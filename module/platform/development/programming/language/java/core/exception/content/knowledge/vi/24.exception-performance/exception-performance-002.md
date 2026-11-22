# Phân biệt chi phí tạo, ném, bắt và ghi log ngoại lệ trong Java

Khi phân tích hiệu năng xử lý exception của Java, câu “`try/catch` rất chậm” thường quá đơn giản và dễ dẫn đến tối ưu hóa sai chỗ. Một đường lỗi thực tế gồm nhiều hoạt động khác nhau: **tạo đối tượng exception**, **thu thập thông tin stack trace**, **ném và chuyển luồng điều khiển**, **tìm và thực thi `catch`**, **chạy cleanup**, sau đó có thể **định dạng và ghi log**. Các hoạt động ấy có chi phí khác nhau, xảy ra ở những thời điểm khác nhau và không phải lúc nào cũng xuất hiện cùng nhau.

Ví dụ, một khối `try` chạy thành công không đồng nghĩa JVM đã tạo exception. Một đối tượng `new IllegalArgumentException(...)` có thể đã tốn chi phí chụp stack trace **ngay lúc tạo**, dù chưa từng bị `throw`. Trái lại, một câu `catch` không được thực thi không có chi phí xử lý lỗi tương đương với ném exception. Trong production, việc in stack trace vào log ở tần suất rất cao có thể chiếm đáng kể CPU, cấp phát, I/O và dung lượng lưu trữ hơn cả phần catch.

Bài này giải thích từng giai đoạn, cách đo cho đúng, những sai lầm về log và các quyết định thiết kế để chỉ trả chi phí của exception khi thật sự cần thiết. Ví dụ sử dụng **Java 17+**.

## 1. Một exception có ít nhất bốn giai đoạn chi phí

Xét đường xử lý sau:

```java
try {
    validate(request);
} catch (InvalidRequestException ex) {
    logger.log(Level.WARNING, "Request không hợp lệ", ex);
}
```

Đây là **đoạn minh họa**, với `validate`, `request`, `InvalidRequestException` và `logger` do ứng dụng định nghĩa. Nếu `validate` chạy bình thường, không có handler nào cần xử lý exception. Nếu nó ném, có thể xảy ra các bước:

| Giai đoạn | Khi nào phát sinh | Công việc có thể tạo chi phí |
| --- | --- | --- |
| **Tạo exception** | Khi gọi constructor/factory của `Throwable` | Cấp phát object; tạo message/cause; mặc định ghi nhận backtrace tại thời điểm xây dựng. |
| **Ném exception** | Khi thực thi `throw` | Thay đổi luồng điều khiển; tìm handler phù hợp; unwinding các frame cần thiết; đi qua `finally` và đóng resource nếu có. |
| **Bắt và xử lý** | Khi đến một `catch` phù hợp | Chạy logic phân loại, đổi nghĩa, tính fallback, thống kê hoặc xử lý nghiệp vụ trong handler. |
| **Ghi log** | Khi code gọi logger/`printStackTrace` hoặc hệ thống quan sát khác | Định dạng thông điệp và stack trace, xử lý cause/suppressed, cấp phát chuỗi, đồng bộ/buffer, ghi console/file/network, tác động lên hàng đợi log. |

Ngoài bốn bước chính còn có chi phí gián tiếp: garbage collection, thay đổi tối ưu hóa JIT, áp lực cấp phát và tác dụng của tầng quan sát (tracing, metrics, log exporter). Các mức chi phí phụ thuộc JVM, loại exception, độ sâu stack, tần suất lỗi và cấu hình logging; **không có một con số nanosecond cố định đúng cho mọi ứng dụng**.

Một cách nhớ:

```text
Luồng thành công:
  kiểm tra → xử lý bình thường → trả kết quả
                   (không cần tạo/throw/catch/log exception)

Luồng thất bại:
  phát hiện lỗi
       ↓
  tạo Throwable (+ stack capture mặc định)
       ↓
  throw / unwind / finally
       ↓
  catch và chính sách phục hồi/báo lỗi
       ↓
  [có thể] format và ghi log
```

Sơ đồ mang tính khái niệm. Có thể **tạo mà không ném**, **ném object đã có**, **catch rồi rethrow**, hoặc **log object chưa từng được ném**. Việc tách giai đoạn giúp đo lường đúng.

## 2. Chi phí tạo exception: constructor và backtrace

Hầu hết exception Java kế thừa `Throwable`. Khi xây dựng một `Throwable` thông thường, constructor của `Throwable` gọi cơ chế thu thập trạng thái stack hiện tại thông qua `fillInStackTrace()`, trừ những cấu hình/implementation đặc biệt. Đó là lý do **tạo exception có thể đắt hơn tạo một object dữ liệu đơn giản**, ngay cả khi chưa ném.

```java
IllegalArgumentException error =
        new IllegalArgumentException("quantity must be positive");

// Chưa có câu lệnh throw, nhưng error đã được khởi tạo.
```

Đoạn trên là snippet hợp lệ trong phương thức Java. Trong JVM thông thường, thông tin vị trí tạo exception đã được ghi nhận; `getStackTrace()` có thể chuyển dữ liệu đó thành mảng `StackTraceElement` để đọc. Việc **thu thập backtrace** và việc **materialize/định dạng stack trace để hiển thị** là các công việc khác nhau: không nên coi `new Exception` và `printStackTrace` có chi phí giống nhau.

Các thành phần quan trọng của construction:

- **Allocation:** cấp phát object; chi phí thay đổi theo cơ chế cấp phát/JIT/GC.
- **Message:** chuỗi có thể có sẵn hoặc được tạo từ phép nối chuỗi, `String.format`, serialize JSON hoặc tính toán khác. Phần tính message trước lời gọi constructor cũng có thể đắt.
- **Cause:** liên kết tới `Throwable` gốc. Giữ cause giúp chẩn đoán, nhưng cây nguyên nhân có thể khiến log stack trace dài hơn.
- **Stack capture:** nhìn nhận ngữ cảnh thực thi khi tạo exception. Số frame và đặc điểm JIT/runtime ảnh hưởng chi phí.
- **Suppressed exceptions:** cấu trúc liên quan khi có nhiều lỗi, đặc biệt với `try-with-resources`. Chỉ phát sinh hoạt động đáng kể khi thật sự cần quản lý các lỗi phụ.

Không phải mọi runtime đều xây dựng biểu diễn stack trace theo cùng một cách; một số tối ưu hóa JVM áp dụng cho các loại lỗi hoặc vị trí ném đặc biệt. **Điều bảo đảm ở mức thiết kế** là không nên dựa vào việc JVM luôn tối ưu bỏ qua giá chụp stack của mọi exception được tạo.

### Tạo message tốn kém dù không ném

```java
IllegalStateException error =
        new IllegalStateException(
                "Invalid payload: " + expensiveSerialization(payload));
```

Đây là snippet minh họa, `payload` và `expensiveSerialization` do ứng dụng định nghĩa. Hàm serialize có thể chạy **trước khi** constructor exception nhận chuỗi. Nếu đoạn này được gọi thường xuyên mà hiếm khi ném, bạn có thể đã đưa chi phí message vào *hot path*.

Tốt hơn, chỉ tạo exception sau khi điều kiện lỗi thực sự được xác nhận:

```java
if (!isValid(payload)) {
    throw new IllegalStateException("Invalid payload");
}
```

Ở đây `isValid` và `payload` là ký hiệu minh họa. Kiểm tra tính hợp lệ vẫn có chi phí và cần thiết về nghiệp vụ, nhưng exception chỉ được tạo ở nhánh lỗi. Nếu cần chẩn đoán sâu, ghi thêm dữ liệu theo chính sách bảo mật và mức log thay vì serialize cả payload vào mọi message lỗi.

## 3. Chi phí ném: điều khiển luồng và unwind

Câu `throw` chuyển điều khiển ra khỏi đường bình thường tới một handler tương thích, hoặc tiếp tục truyền qua các frame gọi cho đến khi có handler hay tới ranh giới uncaught exception. Trong quá trình đó, Java phải thực hiện các `finally` áp dụng và các thao tác cleanup của `try-with-resources` trước khi rời phạm vi.

Ví dụ:

```java
void outer() {
    try {
        inner();
    } finally {
        releaseOwnedResource();
    }
}

void inner() {
    throw new IllegalStateException("failed");
}
```

Đây là snippet minh họa, `releaseOwnedResource` chưa định nghĩa. Khi `inner` ném, việc thoát qua `outer` làm `finally` chạy. Nếu cleanup có I/O hoặc khóa, **chi phí quan sát trong lần thất bại bao gồm cả công việc cleanup**, không đơn thuần là opcode `athrow`.

Cần tách hai việc:

- `throw new MyException(...)`: tạo **rồi** ném. Phép đo quanh câu này bao gồm constructor, stack capture và throw/unwind.
- `throw existingException`: ném lại **cùng object** hiện có; không gọi constructor mới chỉ vì thực thi `throw`.

Ném lại object không mặc nhiên cập nhật stack trace tới vị trí ném mới. Điều này có thể làm thông tin điều tra lỗi kém hữu ích. **Không dùng cache/reuse một exception toàn cục như mẹo tối ưu hóa chung**: stack trace có thể chỉ phản ánh nơi object được tạo, dữ liệu exception có thể bị dùng chung qua nhiều thread và các thông tin cause/suppressed khó quản lý.

Thay vì tối ưu bất chấp khả năng chẩn đoán, hãy xác định có thật sự cần dùng exception như tín hiệu cho tình huống xảy ra hàng triệu lần hay không.

## 4. Chi phí bắt: đừng nhầm `try/catch` với đường ném lỗi

Một khối `try` chứa đường thành công:

```java
int result;
try {
    result = Integer.parseInt("123");
} catch (NumberFormatException ex) {
    result = 0;
}
```

Ở trường hợp này không có `NumberFormatException` được tạo và ném chỉ vì có câu lệnh `catch`. JVM/JIT có thể tối ưu đường xử lý bình thường, mặc dù cấu trúc exception và khả năng xảy ra nhánh lỗi có thể ảnh hưởng một số tối ưu hóa tùy code/JVM.

Khi thực sự vào `catch`:

```java
catch (NumberFormatException ex) {
    failedRecords.incrementAndGet();
    return defaultValue;
}
```

Đây là snippet minh họa, `failedRecords` và `defaultValue` được định nghĩa ở nơi khác. Chi phí **logic trong catch** (counter, tạo giá trị dự phòng, ghi log, thao tác đồng bộ, truy cập DB...) có thể lớn hơn rất nhiều so với việc gán reference exception cho biến `ex`.

Đừng đo `try/catch` bằng cách luôn ném một exception rồi gọi đó là “chi phí của catch”. Đó là **chi phí tổng hợp của đường thất bại**, không chỉ handler.

Một cấu trúc `catch` không thực thi trong đường thành công thường không phải lý do hợp lý để bỏ kiểm tra lỗi. Ngược lại, ném exception để biểu diễn vòng lặp kết thúc bình thường hoặc một kết quả dự kiến xảy ra hàng triệu lần có thể là quyết định thiết kế gây chi phí không cần thiết.

## 5. Chi phí ghi log là một giai đoạn riêng

Ghi log không phải hoạt động bắt buộc của `throw` hoặc `catch`. Nó được kích hoạt khi code ghi nhận exception:

```java
try {
    work();
} catch (IOException ex) {
    logger.log(Level.WARNING, "Không đọc được file", ex);
    throw ex;
}
```

Snippet này giả định `work`, `logger` và `IOException` được khai báo/import. Handler vừa ghi log vừa rethrow, nên **caller vẫn nhận lỗi**. Nếu tầng cao hơn cũng log lại, cùng một sự cố có thể tạo nhiều bản ghi stack trace.

Một bản ghi lỗi có thể gây chi phí ở nhiều nơi:

1. Tính message, ghép chuỗi hoặc tạo object context.
2. Lấy và render stack trace; có thể đi qua cả `cause` và `getSuppressed()`.
3. Định dạng timestamp, thread, MDC/correlation ID, JSON hoặc các trường structured logging.
4. Xếp bản ghi vào hàng đợi hoặc đồng bộ với appender.
5. Ghi console, file, network hoặc hệ thống tập trung.
6. Mở rộng dữ liệu log, tiêu tốn CPU, băng thông, disk, retention và chi phí vận hành.

Với async logger, một phần chi phí có thể dời sang thread khác, nhưng **không biến mất**. Hàng đợi đầy có thể làm block, làm rơi log theo chính sách hoặc tăng độ trễ; cấu hình cụ thể quyết định.

`Throwable.toString()` chủ yếu biểu diễn loại và message, **không tương đương in toàn bộ stack trace**. `printStackTrace()` hoặc logging một `Throwable` dưới dạng stack trace có thể tạo ra nhiều dòng hơn đáng kể. `getStackTrace()` còn có thể materialize dữ liệu frame trước khi format thành text.

### “Logger tắt” không có nghĩa mọi đối số đều miễn phí

Xét:

```java
logger.fine("Trace: " + serializeExpensiveObject(value));
```

Đây là snippet minh họa; `logger` thuộc một logger thích hợp và `serializeExpensiveObject` giả định tồn tại. Java phải đánh giá đối số trước khi gọi method, nên phần serialize/nối chuỗi **vẫn có thể xảy ra** ngay cả khi mức `FINE` không được bật.

Khi dùng `java.util.logging.Logger`, có thể truyền `Supplier<String>` ở API phù hợp để tạo message lười:

```java
logger.log(Level.FINE, () -> "Trace: " + serializeExpensiveObject(value));
```

Snippet này cần import `java.util.logging.Level` và logger tương ứng. Khi level không được bật, cách ghi lười cho phép bỏ qua việc tạo message. Điều đó **không có nghĩa không có bất kỳ overhead nào**: vẫn có chi phí kiểm tra mức log, tạo/điều phối lambda tùy JIT và lời gọi logger.

Khi muốn log `Throwable`, chọn overload phù hợp với framework, ví dụ `logger.log(Level.WARNING, "Lỗi đọc", ex)` của `java.util.logging`. Tránh format stack trace thành chuỗi trước khi đã biết bản ghi có cần xuất hay không.

## 6. Ví dụ Java 17: đếm các giai đoạn mà không giả vờ đo thời gian

Ví dụ dưới đây tách “tạo object”, “ném”, “catch” và “log” bằng counters. Đây là **minh họa thứ tự và nơi phát sinh hoạt động**, không phải benchmark về nanoseconds.

Tạo file `ExceptionPhasesDemo.java`:

```java
public class ExceptionPhasesDemo {

    private static final class InvalidQuantityException
            extends RuntimeException {
        static int constructed;

        InvalidQuantityException(String message) {
            super(message);
            constructed++;
        }
    }

    private static int thrown;
    private static int caught;
    private static int logged;

    private static int addOne(int quantity) {
        if (quantity < 0) {
            InvalidQuantityException error =
                    new InvalidQuantityException("quantity < 0");
            thrown++;
            throw error;
        }
        return quantity + 1;
    }

    private static void recordLog(InvalidQuantityException error) {
        logged++;
        System.out.println("LOG " +
                error.getClass().getSimpleName() +
                ": " + error.getMessage());
    }

    public static void main(String[] args) {
        System.out.println("normal: " + addOne(2));

        InvalidQuantityException onlyCreated =
                new InvalidQuantityException("created only");
        System.out.println("created without throw: "
                + onlyCreated.getMessage());

        try {
            addOne(-1);
        } catch (InvalidQuantityException error) {
            caught++;
            recordLog(error);
        }

        System.out.println("constructed: "
                + InvalidQuantityException.constructed);
        System.out.println("thrown: " + thrown);
        System.out.println("caught: " + caught);
        System.out.println("logged: " + logged);
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 ExceptionPhasesDemo.java
java ExceptionPhasesDemo
```

Stdout:

```text
normal: 3
created without throw: created only
LOG InvalidQuantityException: quantity < 0
constructed: 2
thrown: 1
caught: 1
logged: 1
```

Tại sao có số đếm này?

- `addOne(2)` thành công, không tạo `InvalidQuantityException`.
- `new InvalidQuantityException("created only")` gọi constructor một lần nhưng không ném hoặc log.
- `addOne(-1)` tạo một exception khác, tăng counter `thrown` rồi ném.
- `catch` bắt đúng một lần và gọi `recordLog` một lần.
- Vì vậy số lần tạo là **2**, trong khi số lần ném, bắt và ghi log đều là **1**.

Counter `thrown` trong demo tăng thủ công ngay trước `throw`; nó **không phải cơ chế JVM tự đếm exception**. Đừng đọc các số này như kết quả benchmark thời gian. Mục đích là chứng minh bốn hoạt động khác nhau bằng những điều kiện chạy có thể kiểm tra.

## 7. Minh họa eager và lazy message formatting

Để chứng minh chi phí tạo message có thể phát sinh ngay cả khi không in log, dùng một logger tối giản với `Supplier<String>`. Demo không đại diện cho cấu trúc nội bộ của các logging framework thực.

Tạo file `LazyLogDemo.java`:

```java
import java.util.function.Supplier;

public class LazyLogDemo {

    private static int formattingCalls;

    private static String format(Throwable error) {
        formattingCalls++;
        return error.getClass().getSimpleName()
                + ": " + error.getMessage();
    }

    private static void log(boolean enabled, Supplier<String> message) {
        if (enabled) {
            System.out.println("LOG " + message.get());
        }
    }

    public static void main(String[] args) {
        Throwable error = new IllegalStateException("bad data");

        log(false, () -> format(error));
        System.out.println("lazy disabled: " + formattingCalls);

        String eager = format(error);
        log(false, () -> eager);
        System.out.println("eager disabled: " + formattingCalls);

        log(true, () -> format(error));
        System.out.println("enabled: " + formattingCalls);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 LazyLogDemo.java
java LazyLogDemo
```

Stdout:

```text
lazy disabled: 0
eager disabled: 1
LOG IllegalStateException: bad data
enabled: 2
```

Dòng thứ nhất chứng minh lambda `format(error)` không được gọi khi logger giả lập bị tắt. Trong ví dụ eager, `format(error)` được gọi **trước `log`** nên counter vẫn tăng dù không in. Khi bật, supplier được đánh giá và in một bản ghi.

Bản thân object `error` đã được tạo trước các lệnh log và có chi phí tạo riêng. **Lazy logging chỉ giúp hoãn/bỏ qua phần đánh giá message**, không hoàn tác chi phí của một exception đã được tạo.

Với production logger, ưu tiên API hỗ trợ parameterized/lazy messages hoặc kiểm tra level trước một phép xây dựng context rất đắt. Kiểm tra level thủ công cho mọi log nhỏ không nhất thiết đáng công; nên đo những điểm thực sự nóng.

## 8. Chụp stack trace và định dạng stack trace không phải một việc

Thông tin vị trí lỗi rất hữu ích. Nhưng trong một số thiết kế đặc biệt, người ta muốn giảm chi phí tạo stack trace cho một loại tín hiệu xảy ra cực nhiều lần.

`Throwable` có protected constructor cho phép cấu hình **suppression** và khả năng ghi stack trace (*writable stack trace*). Nếu constructor của subclass gọi `super(message, cause, enableSuppression, writableStackTrace)` với `writableStackTrace=false`, implementation chuẩn sẽ không ghi stack trace cho object đó. Đây là lựa chọn **có đánh đổi lớn về khả năng chẩn đoán**, không phải mặc định nên dùng.

Tạo file `StackTraceChoiceDemo.java`:

```java
public class StackTraceChoiceDemo {

    private static final class LightweightFailure
            extends RuntimeException {
        LightweightFailure(String message) {
            super(message, null, true, false);
        }
    }

    public static void main(String[] args) {
        RuntimeException normal =
                new RuntimeException("normal failure");
        RuntimeException lightweight =
                new LightweightFailure("light failure");

        System.out.println("normal has frames: "
                + (normal.getStackTrace().length > 0));
        System.out.println("light frames: "
                + lightweight.getStackTrace().length);
        System.out.println("light message: "
                + lightweight.getMessage());
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 StackTraceChoiceDemo.java
java StackTraceChoiceDemo
```

Trong JDK 17 thông thường, stdout:

```text
normal has frames: true
light frames: 0
light message: light failure
```

`normal` có backtrace từ lúc tạo. `lightweight` cố ý không giữ stack trace; vẫn có message và vẫn là exception hợp lệ. Tuy nhiên, một log sau này sẽ không cho biết chính xác chuỗi lời gọi tạo exception đó. Khi xử lý bug production, cái giá mất vị trí lỗi có thể cao hơn phần CPU tiết kiệm.

**Chỉ cân nhắc exception không stack trace khi** đây là lựa chọn được thiết kế có chủ đích, có ngữ cảnh chẩn đoán khác, đã có số đo chứng minh chi phí là vấn đề và lỗi không phải trạng thái bất thường cần điều tra đầy đủ. Không tắt stack trace cho mọi exception hoặc exception public quan trọng chỉ để “làm nhanh”.

Java cũng cho phép override `fillInStackTrace()` trong subclass; việc này thay đổi semantics và có thể gây khó chẩn đoán. Đừng sử dụng kỹ thuật đó như mẹo tối ưu chung mà không có test và tài liệu hợp đồng.

## 9. Tái sử dụng exception có thể làm sai thông tin lỗi

Một mẹo thường thấy:

```java
private static final RuntimeException BAD_INPUT =
        new IllegalArgumentException("bad input");

void validate(boolean valid) {
    if (!valid) {
        throw BAD_INPUT;
    }
}
```

Đây là snippet minh họa đặt trong một class. Mỗi lần thất bại không tạo object mới, nhưng `BAD_INPUT` thường có stack trace tại nơi field được khởi tạo, không phải tại điểm kiểm tra gây lỗi cụ thể. Cùng object còn có thể được dùng qua nhiều thread; nếu một nơi bổ sung suppressed exception hoặc thao tác với trạng thái object, việc điều tra trở nên khó hiểu.

Đừng tự động chuyển exception thành singleton vì thấy constructor đắt. Nếu tình huống “bad input” dự kiến xuất hiện ở tần suất cao, cân nhắc việc **trả kết quả validation có kiểu** thay vì ném exception cho mọi trường hợp.

Ngoại lệ tái sử dụng, no-stack exception và thay đổi semantics của stack trace chỉ nên xuất hiện sau khi đã hiểu nhu cầu chẩn đoán, API contract và dữ liệu profiling.

## 10. Khi nào không nên dùng exception làm luồng điều khiển thường xuyên?

Exception thích hợp để thể hiện **đường thất bại, precondition vi phạm hoặc trạng thái đặc biệt theo contract API**. Nhưng nếu một sự kiện xảy ra thường xuyên và được xem như một kết quả bình thường, có thể dùng API không ném lỗi.

Ví dụ tìm kiếm có thể “không thấy” rất thường xuyên:

```java
Optional<String> found = lookup(key);
if (found.isEmpty()) {
    // Đây là một kết quả hợp lệ của truy vấn.
}
```

Đây là snippet minh họa, giả định `lookup` trả `Optional<String>`. Nếu vắng mặt là trạng thái bình thường, `Optional.empty()` hoặc result type có thể rõ hơn việc tạo/ném `NoSuchElementException` cho mỗi lần miss.

Một API parse dữ liệu nhận input người dùng hàng loạt có thể trả:

```java
record ParseResult<T>(T value, String errorCode) {
    boolean isSuccess() {
        return errorCode == null;
    }
}
```

Đây là ví dụ kiểu dữ liệu minh họa với `record` (hỗ trợ trong Java 17), chưa xây dựng parser hoàn chỉnh. API thực cần xác định invariant (ví dụ chỉ một trong value/errorCode hiện diện) và tránh trường hợp `null` mơ hồ.

Tuy nhiên, không phải mọi `NumberFormatException` nên bị thay bằng kiểu result. Nếu chương trình hiếm khi nhận dữ liệu sai, code dùng exception có thể đơn giản, đúng semantics và không đáng tối ưu. **Hiệu năng không phải lý do bỏ validation hoặc che lỗi.**

So sánh:

| Tình huống | Hướng tiếp cận đáng cân nhắc |
| --- | --- |
| Một yêu cầu API hiếm khi vi phạm precondition | Ném exception rõ loại và message. |
| Parser xử lý hàng triệu giá trị, dữ liệu lỗi là tình huống dự kiến | Result/status cho từng record, gom lỗi và báo cáo cuối batch. |
| Kết nối mạng bất ngờ thất bại | Exception/I/O error có ngữ cảnh; xử lý retry theo chính sách. |
| Tra cứu optional key rất thường xuyên không có dữ liệu | `Optional`/kết quả vắng mặt, không biến miss bình thường thành exception burst. |
| Bug invariant nội bộ bị phá | Giữ exception/stack trace để chẩn đoán, không “tối ưu” bằng fallback giả. |

## 11. Vì sao một stack trace log lại có thể rất đắt?

Tạo stack trace và **log stack trace** khác nhau. `Throwable#printStackTrace` có thể duyệt danh sách frame, cause và suppressed exceptions, biến chúng thành text rồi đưa qua `PrintStream`/`PrintWriter`. Logging framework có thể làm điều tương tự với định dạng JSON, MDC và exporter riêng.

Chi phí log có thể tăng theo:

- Số exception mỗi giây.
- Độ sâu stack trace và số chuỗi `caused by`/`suppressed`.
- Kích cỡ metadata log và độ dài message.
- Console sync I/O, tốc độ đĩa, mạng hoặc throughput collector.
- Hàng đợi async bị đầy hoặc việc chuyển sang chế độ block/drop.
- Số lần cùng exception được ghi ở nhiều tầng.

Một lỗi lặp 10.000 lần/phút không chỉ tốn cấp phát exception; nếu mỗi lần ghi hàng chục dòng, logging có thể trở thành tải nặng và gây ra vòng phản hồi: hệ thống đã chậm vì lỗi lại chậm hơn vì log.

### Log ở ranh giới có trách nhiệm

Mẫu dễ gây **double logging**:

```java
try {
    repository.save(entity);
} catch (IOException ex) {
    logger.log(Level.SEVERE, "Repository failed", ex);
    throw ex;
}
```

Nếu service và request handler phía trên cũng log đầy đủ stack trace, một sự cố có thể thành ba bản ghi. Đoạn này chỉ là snippet minh họa; `repository`, `entity`, `logger` phải được định nghĩa đúng ngữ cảnh.

Một hướng thiết kế là:

- Tầng thấp **ném/đổi nghĩa có cause** khi cần, không luôn log.
- Tầng có đủ ngữ cảnh nghiệp vụ quyết định thông điệp và mức log.
- Tầng ngoài cùng hoặc owner workflow ghi một bản ghi lỗi có stack trace nếu thực sự cần.
- Với lỗi input dự kiến, thường log ở mức phù hợp, có thể không cần stack trace trên từng request.
- Dùng counters/metrics cho tần suất lỗi dự kiến; không thay monitoring bằng hàng triệu bản ghi giống nhau.

Không có quy tắc “chỉ được log đúng một lần” cho mọi hệ thống; một số lỗi cần audit và operational logging khác nhau. Nhưng **mỗi bản ghi cần mục đích rõ**, không chỉ để tự bảo đảm “ở đây cũng log”.

## 12. Chọn mức log và sampling theo ý nghĩa lỗi

Một gợi ý thực tế:

| Loại sự kiện | Hướng ghi nhận |
| --- | --- |
| Input validation sai thường gặp | Trả mã lỗi cho caller, đếm metric; log chọn lọc và tránh lộ payload. |
| Lỗi hệ thống bất thường có tác động | Log có stack trace và correlation ID ở tầng chịu trách nhiệm. |
| Lỗi mạng thoáng qua đã retry thành công | Metric retry/tỷ lệ lỗi; log mức phù hợp, tránh ghi full stack cho mỗi attempt nếu không cần. |
| Lỗi lập trình làm hỏng invariant | Giữ nguyên stack/cause; log phục vụ điều tra và cảnh báo. |
| Exception burst do một dependency down | Tăng metric, cảnh báo, có thể rate limit/sample log theo chính sách; không che mất tín hiệu tổng hợp. |

Sampling/rate limiting giúp tránh log storm nhưng cần giữ **số đếm tổng sự kiện** để biết quy mô. Nếu chỉ log 1% mà không có metric tương ứng, bảng log dễ đánh giá thấp mức độ nghiêm trọng.

Không dùng error message hoặc raw stack trace làm metric label có cardinality cực lớn. Ưu tiên loại lỗi, mã lỗi, nhóm subsystem hay thao tác hữu hạn. Dữ liệu nhạy cảm trong message phải được lọc hoặc mã hóa theo chính sách bảo mật.

## 13. try-with-resources, suppressed exception và chi phí cleanup

Khi một hoạt động lỗi, phần chi phí đo ở call-site có thể bao gồm cleanup. Với `try-with-resources`:

```java
try (InputStream in = Files.newInputStream(path)) {
    parse(in);
}
```

Đây là snippet minh họa, cần import `InputStream`, `Files` và biến `path`, hàm `parse`. Nếu `parse` ném exception, Java vẫn gọi `in.close()`. Nếu close cũng ném exception, exception close thường được gắn bằng `addSuppressed` vào primary exception.

Do đó, một benchmark đo `throw new IOException` bên trong resource scope có thể đang đo:
1. Constructor và stack capture của IOException chính.
2. Throw/unwind.
3. I/O cleanup (`close`), có thể đắt hơn nhiều.
4. Nếu close thất bại, tạo/cấp phát thêm exception và ghi suppressed state.
5. Catch/log phía bên ngoài nếu được gọi.

Đừng xem kết quả đó là chi phí thuần của opcode throw hay handler.

Quan trọng hơn: **không bỏ cleanup để giảm latency**. Rò rỉ file descriptor, connection, socket hay lock thường tệ hơn chi phí xử lý exception. Tối ưu đúng là sắp xếp quyền sở hữu, thời điểm đóng và xử lý lỗi phù hợp.

## 14. Checked và unchecked exception có tạo khác biệt hiệu năng không?

`IOException` là checked, `IllegalStateException` là unchecked. Quy tắc kiểm tra ở compile time khác nhau: checked exception phải được khai báo hoặc bắt theo luật Java; unchecked không bắt buộc. Nhưng **không có quy tắc chung** rằng checked exception luôn có chi phí runtime cao hơn hoặc thấp hơn unchecked chỉ vì chữ ký `throws`.

Sự khác biệt về chi phí thường đến từ:
- Loại exception, constructor/message và cách stack trace được xử lý.
- Tần suất tạo/ném.
- Độ sâu stack hoặc cleanup khi unwind.
- Logic của handler và logging.
- Kỹ thuật tối ưu của JIT và đặc tính runtime.

Không chuyển toàn bộ `IOException` thành `RuntimeException` chỉ với lý do “unchecked nhanh hơn”. Chuyển exception có thể hợp lý ở boundary để ổn định contract hoặc thêm context, nhưng việc tạo wrapper mới lại có thể thu thập một stack trace khác; nếu còn giữ cause, log đầy đủ có thể in cả hai chuỗi thông tin.

## 15. Các bẫy benchmark về hiệu năng exception

Microbenchmark tự viết kiểu:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    try {
        throw new RuntimeException("failed");
    } catch (RuntimeException ignored) {
    }
}
System.out.println(System.nanoTime() - start);
```

Đây là snippet minh họa về **benchmark không đủ tin cậy**, không phải phép đo dùng để ra quyết định production. Nó trộn **construction + throw + catch**, có thể chịu tối ưu hóa JIT/GC, quá trình warm-up, môi trường CPU, mức log khác nhau và ảnh hưởng của code bị compiler chứng minh không có side effect có ích. Chạy một lần và lấy số nanosecond không đủ kết luận.

### Vì sao benchmark ngây thơ sai?

**Warm-up và JIT:** Những lần chạy đầu thường bao gồm class loading, compilation và trạng thái code chưa được tối ưu. Đường exception thường hiếm trong production nhưng benchmark lại ném liên tục, tạo profile hoàn toàn khác.

**Escape analysis và tối ưu:** JIT có thể tối ưu cấp phát/đường đi khác với dự đoán từ source, hoặc code không có kết quả quan sát bị loại bỏ. Benchmark phải đảm bảo thực hiện công việc có nghĩa.

**HotSpot fast-throw:** Một số bản HotSpot có tối ưu đặc biệt với một số exception **do JVM tự tạo** tại các vị trí lỗi lặp (ví dụ implicit null/bounds checks); stack trace có thể bị lược bỏ trong một số điều kiện. Kết quả không được suy rộng sang `throw new MyDomainException(...)` hoặc mọi JVM/JDK. Flag/runtime/version ảnh hưởng hành vi; cần xác minh JVM đích trước khi suy luận.

**Độ sâu và vị trí stack:** Tạo lỗi ở phương thức sâu có thể khác tạo lỗi ở đỉnh stack; `throw` qua nhiều frame/`finally` khác catch tại chỗ.

**Log level:** Benchmark ghi stack trace ra console/file không thể so sánh trực tiếp với đường chỉ `catch` rồi trả fallback. Log stdout/stderr còn phụ thuộc buffering và môi trường terminal.

**GC và allocation:** Vòng lặp tạo nhiều Throwable gây áp lực allocation; cần đo thêm throughput/allocations/GC, không chỉ thời gian một lần gọi.

**Branch probability:** Nếu 0,001% request lỗi, chi phí trung bình trên request rất khác khi test luôn throw 100%. Cần đo cả hot path thành công và error burst.

### Cách đo đúng hơn

Đối với microbenchmark Java, nên dùng **JMH (Java Microbenchmark Harness)**, có warm-up, nhiều iteration/fork và cơ chế hạn chế một số bẫy JIT/benchmark. JMH là thư viện/harness bên ngoài JDK, không có sẵn chỉ từ `javac`; cần thiết lập project/dependency phù hợp trước khi chạy.

Thiết kế các phép đo riêng:

1. **Successful path:** có `try/catch` nhưng không tạo exception.
2. **Construct-only:** tạo Throwable nhưng không `throw` và không log; đảm bảo object là kết quả quan sát được.
3. **Throw pre-created:** ném object có sẵn để cô lập gần hơn phần throw/catch, nhưng ghi rõ semantics stack trace khác đường thông thường.
4. **Throw new:** tạo và ném trong cùng nhánh; đại diện cho tình huống phổ biến nhưng không phải chi phí “ném thuần”.
5. **Catch + lightweight handling:** có phân loại/trả fallback mà không log.
6. **Catch + log disabled:** kiểm tra overhead của logging call và argument evaluation.
7. **Catch + log enabled:** đo format và appender thực; với async cần tính tải consumer/hàng đợi.
8. **Different stack depths/error rates:** kiểm tra ảnh hưởng độ sâu frame, các loại exception và tần suất lỗi.

Phân biệt **microbenchmark** với **profiling của ứng dụng thật**. Một thay đổi tối ưu constructor có thể chẳng ảnh hưởng p95 latency nếu network/I/O mới là bottleneck. Hãy kết hợp CPU profile, allocation profile, GC logs, log throughput và metrics của đường lỗi trước khi quyết định.

## 16. Ví dụ mã đo minh họa: cách tổ chức phép thử, không suy diễn số cố định

Ví dụ dưới đây in số lượng thao tác chứ **không** cố tạo benchmark từ `System.nanoTime`:

Tạo file `ErrorPathClassificationDemo.java`:

```java
public class ErrorPathClassificationDemo {

    private static int created;
    private static int handled;

    private static IllegalArgumentException newFailure() {
        created++;
        return new IllegalArgumentException("invalid");
    }

    private static boolean validate(int value) {
        if (value >= 0) {
            return true;
        }
        throw newFailure();
    }

    private static void process(int[] input) {
        for (int value : input) {
            try {
                validate(value);
            } catch (IllegalArgumentException ex) {
                handled++;
            }
        }
    }

    public static void main(String[] args) {
        process(new int[] {1, 2, -1, 3, -2, 4});
        System.out.println("items: 6");
        System.out.println("created: " + created);
        System.out.println("handled: " + handled);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ErrorPathClassificationDemo.java
java ErrorPathClassificationDemo
```

Stdout:

```text
items: 6
created: 2
handled: 2
```

Bài toán kiểm tra sáu đầu vào, chỉ hai giá trị âm đi qua đường exception. Đối với việc benchmark, ta sẽ cần chạy nhiều tỉ lệ lỗi (0%, 1%, 50%, 100%) với dữ liệu có ý nghĩa và harness phù hợp. **Không lấy 2/6 rồi kết luận 33% CPU dành cho exception**; đây chỉ là tỉ lệ item lỗi trong dữ liệu mẫu.

Khi kiểm tra hiệu năng production, đo **số lỗi trên mỗi request, số exception object được cấp phát, chi phí ghi log và latency tăng thêm**, thay vì chỉ nhìn số lần `catch` xuất hiện trong source code.

## 17. Thiết kế API sao cho ít lỗi nhưng vẫn dễ chẩn đoán

Một thiết kế cân bằng thường có các nguyên tắc:

**Dùng exception cho thất bại đáng được coi là exceptional.** Mọi vi phạm ràng buộc nghiêm trọng hoặc lỗi bất ngờ cần đường xử lý rõ. Đừng xóa `throw` vì sợ overhead nếu hiếm khi xảy ra.

**Dùng result type cho tình huống dự kiến tần suất cao.** Ví dụ parser batch nhận lỗi mỗi record là bình thường; trả trạng thái thay vì ném exception hàng triệu lần có thể có lợi và giúp người gọi phân loại chính xác.

**Tạo exception tại thời điểm biết có lỗi.** Tránh pre-construct object hoặc format thông điệp đắt trên successful path.

**Giữ cause khi dịch exception.** Tầng persistence có thể đổi `SQLException` thành `RepositoryUnavailableException` để ổn định hợp đồng, nhưng giữ `cause` để chẩn đoán. Việc tạo wrapper có chi phí; chỉ làm khi thực sự có giá trị về abstraction.

**Ghi log tại ranh giới hợp lý.** Khi bắt rồi rethrow, không bắt buộc phải log thêm stack trace tại chỗ. Caller thường có ngữ cảnh tốt hơn để quyết định mức severity và response.

**Bảo toàn lỗi và cleanup.** Dùng `try-with-resources`/`finally` đúng quyền sở hữu, phân biệt primary/cause/suppressed. Không hy sinh cleanup để cải thiện con số benchmark.

**Đừng làm logging biến validation error thành nguồn phát tán dữ liệu.** Không ghi nguyên token, thông tin xác thực, payload cá nhân vào message exception hay log.

**Quan sát bằng metrics có cardinality ổn định.** Đếm lỗi theo loại và hệ thống, thay vì gắn nguyên message/stack làm label.

## 18. So sánh các chiến lược trên tình huống thực tế

### Tình huống A: API nhận input sai với tần suất nhỏ

Giải pháp có thể là:

```java
if (quantity <= 0) {
    throw new IllegalArgumentException("quantity must be positive");
}
```

Đây là precondition rõ ràng. Nếu caller gửi sai hiếm, chi phí tạo/ném chỉ xảy ra ở nhánh lỗi. Handler HTTP có thể trả phản hồi 400, thống kê tỉ lệ validation và tránh in stack trace đầy đủ của mỗi yêu cầu nếu không cần.

### Tình huống B: import một triệu bản ghi, 30% bản ghi không hợp lệ

Đổi mọi record lỗi thành exception rồi log full stack sẽ tạo nhiều object và bản ghi lặp. Có thể dùng một result/status cho mỗi record, thu thập các mã lỗi, chỉ xuất báo cáo/tổng hợp theo batch. Khi phát sinh lỗi hệ thống bất thường trong quá trình import, exception với stack trace vẫn hữu ích.

### Tình huống C: dependency mạng lỗi theo đợt

Đôi khi chính việc gọi network chậm hơn nhiều so với constructor exception. Nhưng khi lỗi diện rộng, ghi log lặp ở mọi lớp tạo log storm. Dùng retry có giới hạn, circuit breaker nếu cần, metrics/tỷ lệ lỗi, sampling log và một nơi ghi thông điệp đủ ngữ cảnh. Không đánh giá “tăng tốc” chỉ bằng cách bỏ stack trace nếu bottleneck thật sự là network hoặc queue.

### Tình huống D: thư viện tạo exception trước để dùng cho nhiều request

Khi lỗi hiếm, pre-construct exception có thể đưa chi phí tạo vào startup và làm mất stack của vị trí request cụ thể. Nếu cache exception dùng chung, chẩn đoán có thể sai và suppressed/cause có thể bị chia sẻ. Chỉ làm khi có hợp đồng rõ ràng và thực sự được đo/kiểm chứng; đa số trường hợp nên tạo exception khi thất bại.

### Tình huống E: logger ở mức DEBUG tắt trong production

Nếu code vẫn gọi một formatter rất nặng trước logger, tắt log level chưa chắc đã bỏ chi phí chuẩn bị message. Dùng lazy/parameterized logging hoặc guard level cho biểu thức đắt; profile sau thay đổi để xác nhận lợi ích.

## 19. Lỗi thường gặp và cách sửa

**“Chỉ có `try/catch` cũng làm chương trình chậm tương đương ném lỗi.”** Sai. Đường không lỗi thường không tạo và ném exception; cần phân biệt xử lý bình thường với exception path.

**“Chi phí throw bằng chi phí new.”** Sai. Constructor/backtrace và throw/unwind là các giai đoạn khác nhau; `throw new` trộn cả hai.

**“Catch là giai đoạn tốn nhất.”** Không có quy tắc như vậy. Logic trong catch, log stack trace, I/O và cleanup có thể chiếm phần lớn chi phí.

**“Log level OFF thì không có chi phí.”** Đối số được tính trước lời gọi vẫn có thể tốn CPU/cấp phát. Dùng API lazy/parameterized để tránh phần format đắt khi không cần.

**“Chỉ cần `error.toString()` là đã in stack trace.”** Không. `toString` thường trả loại + message; `printStackTrace` và logging Throwable đầy đủ có thêm frame/cause/suppressed.

**“Log exception tại mọi tầng mới an toàn.”** Có thể tạo nhiều bản ghi cho cùng failure và che tín hiệu thật trong log storm. Ghi tại boundary có trách nhiệm, giữ cause khi truyền tiếp.

**“Cứ tắt stack trace để tăng tốc.”** Có thể làm mất thông tin điều tra critical bug. Tối ưu no-stack chỉ khi contract cho phép và profiling chứng minh lợi ích.

**“Reuse singleton exception luôn nhanh và an toàn.”** Dễ dẫn đến stack trace sai nơi ném và object dùng chung giữa nhiều thread. Tránh nếu chưa có lý do rõ ràng.

**“Checked exception đắt hơn unchecked exception vì compiler yêu cầu catch.”** Đây là quy tắc kiểu tại compile time, không phải bảng xếp hạng runtime overhead.

**“Dùng System.nanoTime một vòng lặp là đủ chứng minh.”** Microbenchmark cần warm-up, nhiều mẫu, chống JIT elimination và môi trường đo nhất quán; nên dùng JMH và xác minh trên workload thật.

**“Exception ít nhưng có rất nhiều log nên chắc bottleneck tại throw.”** Không. Cần đo riêng formatting, stack rendering và appender/hàng đợi log.

**“Bỏ finally/close để giảm chi phí khi lỗi.”** Cleanup đúng là một phần invariant. Tối ưu hóa làm rò rỉ tài nguyên là sai mục tiêu.

## 20. Checklist trước khi tối ưu

1. **Chi phí đang nằm ở đâu?** Constructor/stack capture, unwind, catch logic, cleanup, message formatting hay appender log?
2. **Tần suất nhánh lỗi thực tế?** 0,001%, 1%, 50% hay error burst 100%? Đường nóng của ứng dụng là gì?
3. **Exception có là kết quả dự kiến thường xuyên không?** Nếu có, `Optional`/status/result type có làm hợp đồng rõ hơn không?
4. **Có xây dựng message/format JSON trước khi biết cần lỗi/log không?** Có thể tạo lười không?
5. **Có log cùng failure ở nhiều tầng không?** Có thể giữ một event/metric rõ ownership không?
6. **Đang in full stack trace cho mọi lỗi input có tính dự kiến không?** Có thể dùng metric và sample log phù hợp không?
7. **Có giữ được cause, suppressed, cleanup và trạng thái thread không?** Đừng đánh đổi tính đúng đắn.
8. **Có cần stack trace để debug production không?** Nếu có, không vội dùng no-stack exception.
9. **Benchmark có tách các pha và chống sai lệch JIT/GC chưa?** Dùng JMH khi cần số microbenchmark.
10. **Kết quả có cải thiện production không?** Đối chiếu p95/p99 latency, allocation rate, CPU, GC, log throughput, queue drops và tốc độ xử lý.
11. **Có rủi ro vận hành hoặc bảo mật mới không?** Rate-limit log nhưng vẫn giữ metrics; không đưa dữ liệu nhạy cảm vào message.
12. **Regression test còn kiểm tra đúng lỗi không?** Tối ưu performance không được biến thất bại thành thành công giả hoặc thay đổi hợp đồng công khai ngoài ý muốn.

## 21. Tổng kết

**Tạo, ném, bắt và ghi log exception là bốn công việc khác nhau**. Trong Java thông thường, constructor `Throwable` có thể thu thập stack ngay khi tạo; `throw` chuyển luồng điều khiển và unwind; `catch` chạy logic xử lý; logger có thể format stack trace rồi đẩy dữ liệu qua I/O/hàng đợi. Đường thành công chỉ đi qua `try` không phải đã trả đủ mọi chi phí của đường exception.

Tối ưu hiệu quả thường bắt đầu bằng **không tạo exception trên hot path bình thường**, **không dùng exception cho kết quả dự kiến tần suất cao**, **không format log vô ích**, và **không ghi trùng stack trace ở nhiều tầng**. Khi cần số liệu, tách các thành phần khi benchmark, dùng JMH phù hợp và xác nhận bằng profiling workload thật. Vẫn phải giữ nguyên invariant, cleanup, thông tin cause/stack trace cần thiết và khả năng quan sát lỗi: hiệu năng tốt chỉ có ý nghĩa khi hệ thống tiếp tục đúng và có thể chẩn đoán.