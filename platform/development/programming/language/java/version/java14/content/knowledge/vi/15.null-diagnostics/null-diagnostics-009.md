# Chẩn đoán null: giữ stack trace và nguyên nhân ngoại lệ khi ghi nhật ký trong Java

## 1. Mục tiêu: log đủ thông tin để tìm được nơi phát sinh `NullPointerException`

Khi một đối tượng hoặc một giá trị trung gian là `null`, Java có thể ném `NullPointerException` (NPE). Vấn đề khi điều tra không chỉ là biết **có NPE**, mà còn phải trả lời:

- Thao tác nào đang thực hiện khi lỗi xảy ra: xử lý yêu cầu, tính phí, cập nhật đặt chỗ hay đọc dữ liệu?
- Lỗi phát sinh từ **method và vị trí mã nguồn nào**?
- Ngoại lệ đang thấy có phải lỗi gốc, hay chỉ là một **ngoại lệ mới được bọc lại** để bổ sung ngữ cảnh nghiệp vụ?
- Nếu có nhiều lỗi liên quan (ví dụ lỗi xử lý chính và lỗi đóng tài nguyên), ta có còn nhìn được cả những lỗi **suppressed** không?

Vì vậy, trong quá trình ghi nhật ký (**logging**), cần giữ **đối tượng `Throwable`**, không chỉ giữ vài chữ trong thông báo. `Throwable` mang theo:

1. **`getMessage()`:** mô tả bằng văn bản; có thể là `null` và không bảo đảm đủ để chẩn đoán.
2. **`getStackTrace()`:** những `StackTraceElement` mô tả ngăn xếp tại thời điểm ngoại lệ được tạo/ghi lại; thường chứa class, method và vị trí dòng khi có thông tin biên dịch.
3. **`getCause()`:** tham chiếu đến ngoại lệ đã gây ra ngoại lệ hiện tại, tạo thành **chuỗi nguyên nhân** (*cause chain*).
4. **`getSuppressed()`:** những ngoại lệ bổ sung bị nén lại, điển hình khi `try-with-resources` gặp lỗi đóng tài nguyên trong lúc xử lý ngoại lệ chính.

**Quy tắc cốt lõi:** Ghi **ngữ cảnh nghiệp vụ an toàn** cùng với **`Throwable` gốc hoặc ngoại lệ bọc có `cause` chính xác**; để logging framework/formatter xử lý stack trace. Đừng đổi ngoại lệ thành một `String` rồi nghĩ rằng thông tin chẩn đoán vẫn đầy đủ.

**Phiên bản:** Tài liệu tập trung các API và cách xử lý **hiện còn dùng trong Java 17+**. Cơ chế NPE thông báo chi tiết được giới thiệu trong **Java 14 (JEP 358)**, mặc định bật từ Java 15 trên HotSpot/Oracle JDK tương ứng. Quy tắc ghi log và bảo toàn cause dưới đây **không phụ thuộc** phải biết trước chính xác nội dung thông báo NPE của JVM.

## 2. Sai lầm phổ biến: chỉ ghi chuỗi thông báo

Xét một đoạn xử lý (snippet nằm trong một phương thức có `logger` và `request`):

```java
try {
    process(request);
} catch (NullPointerException e) {
    logger.severe("Lỗi: " + e.getMessage());
}
```

Đoạn trên chỉ chuyển một phần thông tin thành **chuỗi ký tự**. Một handler/formatter nhận được thông điệp đó không tự có đối tượng ngoại lệ để hiển thị nơi lỗi xảy ra, cause và các lỗi suppressed. Nếu `getMessage()` trả `null`, log có thể chỉ ghi `Lỗi: null`.

Ngay cả:

```java
logger.severe("Lỗi: " + e);
```

cũng chưa tương đương với ghi `Throwable`. Nối chuỗi ở đây sẽ gọi `Throwable.toString()`, thường chỉ gồm **tên loại exception + message**, **không kèm toàn bộ stack trace**.

Cách đúng với API chuẩn `java.util.logging` (JUL):

```java
logger.log(
        java.util.logging.Level.SEVERE,
        "Không thể xử lý requestId=R-7",
        e);
```

Chữ ký phương thức là:

```java
void Logger.log(Level level, String msg, Throwable thrown)
```

Tham số thứ ba là **`Throwable`**, không phải một chuỗi đã được tạo bằng `e.getMessage()`. JUL đưa ngoại lệ này vào trường `thrown` của `LogRecord`; formatter/handler có thể hiển thị đầy đủ stack trace và chuỗi nguyên nhân theo cấu hình.

> **Phân biệt lưu giữ với hiển thị:** Đưa `e` vào tham số `Throwable` làm `LogRecord` lưu được tham chiếu ngoại lệ. Nhưng việc log cuối cùng có được xuất, giữ nguyên, gửi tới hệ thống tập trung hoặc hiển thị bao nhiêu dòng còn phụ thuộc **log level, filter, handler, formatter và cấu hình vận hành**. Không khẳng định mọi cấu hình logger đều tự in đầy đủ stack trace.

### Bảng so sánh ngắn

| Cách ghi | Thông tin gửi tới JUL | Kết luận |
| --- | --- | --- |
| `logger.severe(e.getMessage())` | `String` message | Thiếu đối tượng Throwable/stack trace/cause |
| `logger.severe(e.toString())` | `String` chứa tên lớp + message | Vẫn không gửi Throwable |
| `logger.log(Level.SEVERE, "Lỗi", e)` | Message **và** `Throwable` | Đúng để formatter xử lý stack/cause |
| `logger.log(Level.SEVERE, "Lỗi", e.getCause())` | Chỉ cause được chọn | Có thể làm mất **ngoại lệ bao ngoài** và ngữ cảnh tại tầng hiện tại |
| `logger.log(Level.SEVERE, e, () -> "Lỗi")` | Throwable và lazy message | Dạng overload hiện hành khi cần dựng thông điệp lazily |

Dòng cuối sử dụng overload có chữ ký `log(Level, Throwable, Supplier<String>)`; `Supplier` được gọi khi cần log theo mức log có hiệu lực. Với đoạn mã thông thường, `log(Level, String, Throwable)` đã rõ ràng và đủ dùng.

## 3. Giữ cause khi chuyển đổi ngoại lệ giữa các tầng

Giả sử tầng xử lý ban đầu gặp `NullPointerException` nhưng tầng service muốn cung cấp ngữ cảnh nghiệp vụ bằng ngoại lệ `ProcessingException`.

**Không nên tạo exception mới rồi bỏ mất lỗi gốc:**

```java
try {
    extractEmail(request);
} catch (NullPointerException e) {
    throw new ProcessingException("Không xử lý được request");
}
```

Nếu constructor của `ProcessingException` chỉ nhận `String` thì ngoại lệ được tạo có **stack trace ở nơi bọc lỗi**, nhưng **không có cause tham chiếu tới NPE ban đầu**. Log phía ngoài chỉ còn hình ảnh lỗi tại tầng service và khó lần ngược tới biểu thức gây null.

**Đúng hơn: truyền cause vào constructor:**

```java
static class ProcessingException extends RuntimeException {
    ProcessingException(String message, Throwable cause) {
        super(message, cause);
    }
}

// Minh họa trong method xử lý:
try {
    extractEmail(request);
} catch (NullPointerException cause) {
    throw new ProcessingException(
            "Không xử lý được request R-7", cause);
}
```

Đây là **các đoạn minh họa**, không phải một tệp Java độc lập; xem chương trình đầy đủ ở phần sau. Constructor `super(message, cause)` bảo toàn **tham chiếu tới ngoại lệ gốc**, bao gồm stack trace mà nó mang theo. Ngoại lệ mới có stack trace riêng tại điểm bọc lỗi; `getCause()` giúp lần theo stack trace cũ.

Chuỗi chẩn đoán có dạng:

```text
ProcessingException: Không xử lý được request R-7
    at Service.process(...)
Caused by: NullPointerException: ...
    at Service.extractEmail(...)
```

Đây chỉ là **hình dung cấu trúc**, không phải output nguyên văn cố định của một JVM hay formatter cụ thể. Class, method, file, line number, thông báo NPE và cách in `Caused by` có thể thay đổi giữa môi trường.

### Giữ cả hai cấp ngữ cảnh

- **Ngoại lệ bao ngoài:** mô tả thao tác cấp nghiệp vụ bị thất bại và vị trí code nơi lỗi được chuyển đổi.
- **Cause:** giữ lỗi kỹ thuật ban đầu, như NPE tại `extractEmail`, và ngăn xếp giúp tìm chỗ dereference `null`.
- **Logger ở ranh giới xử lý:** ghi ngoại lệ bao ngoài **một lần**, trong đó cause vẫn còn nguyên; không cần ghi mỗi tầng thành một lỗi độc lập.

Khi cần truyền thẳng cùng một ngoại lệ lên tầng gọi mà không bổ sung thông điệp hay chuyển loại, có thể **`throw e;`**. Trong Java, cách này ném lại **cùng một đối tượng ngoại lệ**, không tự tạo một đối tượng khác. Cần phân biệt với `throw new RuntimeException(...)`: ngoại lệ mới có stack của nơi được tạo và sẽ mất cause nếu không truyền `e`.

**Không tự ý gọi `fillInStackTrace()` chỉ để log**, vì phương thức này có thể ghi đè thông tin ngăn xếp hiện tại trong ngoại lệ. Thao tác đúng thông thường là giữ `Throwable` và truyền cho logger.

## 4. Ví dụ hoàn chỉnh Java 17+: logger nhận Throwable, giữ NPE gốc và lỗi suppressed

Tạo tệp **`NullLoggingDemo.java`** sau. Ví dụ dùng **Java Util Logging** có sẵn trong JDK, không cần thư viện bên ngoài. Để kiểm thử chắc chắn mà không phụ thuộc timestamp hay định dạng console log, chương trình dùng một `Handler` nhỏ để giữ `LogRecord` trong bộ nhớ, rồi kiểm tra trường `thrown`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class NullLoggingDemo {
    record Customer(String email) {}
    record Request(String id, Customer customer) {}

    static class ProcessingException extends RuntimeException {
        ProcessingException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class CaptureHandler extends Handler {
        final List<LogRecord> records = new ArrayList<>();

        @Override public void publish(LogRecord record) {
            if (isLoggable(record)) {
                records.add(record);
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    static final class FailClose implements AutoCloseable {
        @Override public void close() {
            throw new IllegalStateException("close-failed");
        }
    }

    static String extractEmail(Request request) {
        return request.customer().email().strip();
    }

    static void process(Request request) {
        try {
            extractEmail(request);
        } catch (NullPointerException cause) {
            throw new ProcessingException(
                    "Cannot process request " + request.id(), cause);
        }
    }

    static void resourceFailure() {
        try (FailClose resource = new FailClose()) {
            throw new IllegalStateException("primary-failed");
        }
    }

    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lesson.null.logging.demo");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        CaptureHandler handler = new CaptureHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        try {
            try {
                process(new Request("R-7", null));
                throw new AssertionError("Expected ProcessingException");
            } catch (ProcessingException exception) {
                logger.log(Level.SEVERE,
                        "requestId=R-7 processing failed", exception);

                LogRecord logged = handler.records.get(0);
                Throwable root = exception.getCause();
                check(logged.getThrown() == exception, "lost wrapper");
                check(root instanceof NullPointerException, "lost cause");
                check(root.getStackTrace().length > 0, "missing stack");
                check(root.getStackTrace()[0].getMethodName()
                        .equals("extractEmail"), "wrong root frame");

                System.out.println("level=" + logged.getLevel());
                System.out.println("attachedThrowable="
                        + (logged.getThrown() == exception));
                System.out.println("causeType="
                        + root.getClass().getSimpleName());
                System.out.println("causeAt="
                        + root.getStackTrace()[0].getMethodName());
                System.out.println("chainPreserved="
                        + (exception.getCause() == root));
                System.out.println("context=" + logged.getMessage());
            }

            try {
                resourceFailure();
                throw new AssertionError("Expected IllegalStateException");
            } catch (IllegalStateException exception) {
                logger.log(Level.WARNING, "resource failure", exception);

                LogRecord logged = handler.records.get(1);
                check(logged.getThrown() == exception, "lost suppression");
                check(exception.getSuppressed().length == 1,
                        "missing suppressed");

                System.out.println("suppressedCount="
                        + exception.getSuppressed().length);
                System.out.println("suppressedCause="
                        + exception.getSuppressed()[0].getMessage());
                System.out.println("loggedSuppressed="
                        + (logged.getThrown() == exception));
            }
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
```

**Biên dịch và chạy** bằng JDK 17+:

```bash
javac --release 17 -encoding UTF-8 NullLoggingDemo.java
java NullLoggingDemo
```

**Standard output đã kiểm thử:**

```text
level=SEVERE
attachedThrowable=true
causeType=NullPointerException
causeAt=extractEmail
chainPreserved=true
context=requestId=R-7 processing failed
suppressedCount=1
suppressedCause=close-failed
loggedSuppressed=true
```

**Lưu ý về output:** Đây là các dòng `System.out.println` dùng để kiểm tra **đối tượng `LogRecord`**, **không phải mẫu định dạng console log**. Trong ví dụ, `setUseParentHandlers(false)` ngăn log chuyển lên parent handler, còn `CaptureHandler` không in ra màn hình. Do đó không có timestamp thay đổi hoặc hàng chục dòng stack trace làm đầu ra không cố định. Với handler/formatter thực tế, log ngoại lệ có thể xuất ra console, tệp hoặc hệ thống log theo cấu hình.

### 4.1. Đường đi của NPE và cause

Lệnh:

```java
process(new Request("R-7", null));
```

tạo `Request` có `customer` bằng `null`. Trong `extractEmail`, chương trình thực hiện:

```java
return request.customer().email().strip();
```

Sau khi `customer()` trả `null`, lời gọi `email()` trên `null` gây NPE. `process` bắt đúng NPE này và tạo `ProcessingException` với `cause` gốc.

Ở tầng ngoài, logger nhận **`exception` bao ngoài**:

```java
logger.log(Level.SEVERE,
        "requestId=R-7 processing failed", exception);
```

`LogRecord.getThrown()` trả lại **đúng tham chiếu đối tượng bao ngoài**, nên:

- `attachedThrowable=true`: bản ghi log thực sự có `Throwable`, không chỉ message.
- `causeType=NullPointerException`: cause vẫn là NPE ban đầu.
- `causeAt=extractEmail`: phần tử đầu tiên trong stack trace của cause chỉ tới phương thức làm phát sinh lỗi ở **môi trường JVM được kiểm thử**.
- `chainPreserved=true`: `ProcessingException` trỏ tới cùng cause gốc.
- `context=requestId=R-7 processing failed`: bản ghi còn chứa ngữ cảnh tác vụ, tách khỏi nội dung exception.

**Không kiểm tra số dòng stack trace cố định** hoặc so sánh nguyên văn thông báo NPE theo từng phiên bản JVM. Trình biên dịch, chế độ tối ưu và cách formatter xử lý stack có thể khác nhau. Đối với ứng dụng thực tế, ưu tiên test **kiểu cause và sự tồn tại/chính xác của chuỗi cause**, rồi kiểm tra những frame quan trọng khi môi trường thử nghiệm bảo đảm có chúng.

### 4.2. Lỗi suppressed khi đóng tài nguyên

`resourceFailure()` cố ý ném `IllegalStateException("primary-failed")` trong thân `try-with-resources`. Khi thoát `try`, `FailClose.close()` cũng ném `IllegalStateException("close-failed")`.

Trong Java, **lỗi chính** vẫn là `primary-failed`; lỗi xảy ra lúc đóng tài nguyên được **gắn thành suppressed exception** trong lỗi chính. Do vậy:

```java
exception.getSuppressed().length == 1
exception.getSuppressed()[0].getMessage().equals("close-failed")
```

Đoạn này là **điều kiện minh họa** bên trong khối bắt lỗi. Khi ghi:

```java
logger.log(Level.WARNING, "resource failure", exception);
```

bản ghi giữ **đúng Throwable mang danh sách suppressed**. Formatter phù hợp có thể trình bày cả `Suppressed: ...` bên dưới stack trace. Nếu chỉ log `exception.getMessage()` thì thông tin về lỗi đóng tài nguyên sẽ mất khỏi dữ liệu log này.

### 4.3. Vì sao dùng `Handler` riêng trong demo?

`java.util.logging` cho phép nhiều `Handler` và `Formatter` với cấu hình khác nhau. Nếu dựa vào log thực sự in ra `System.err`, đầu ra sẽ chứa timestamp, class/method và dòng stack trace có thể đổi theo môi trường.

Trong chương trình này, `CaptureHandler` chỉ thu `LogRecord`. Nó chứng minh hai thông tin quan trọng mà không phụ thuộc định dạng:

1. **JUL nhận đối tượng ngoại lệ nào** trong `getThrown()`.
2. **Chuỗi nguyên nhân và suppressed** vẫn còn khi truy cập đối tượng đó.

Đây là một `Handler` đơn giản dành cho **test một luồng**. Trong production, handler phải tuân thủ yêu cầu đồng thời, vòng đời và bảo mật của hệ thống logging; không dùng nguyên xi `ArrayList` không đồng bộ này làm bộ thu log đa luồng.

## 5. Helpful NullPointerExceptions trong Java hiện hành

Java 14 bổ sung *Helpful NullPointerExceptions* (JEP 358). Đối với những NPE do JVM phát hiện khi thực hiện bytecode truy cập trên `null`, JVM có thể tạo thông điệp chi tiết hơn, giúp thấy **biểu thức nào là `null`**.

Ví dụ:

```java
// Đặt trong phương thức có Object request hoặc record Request phù hợp.
String email = request.customer().email().strip();
```

Nếu `request.customer()` trả `null`, một JVM hiện đại có hỗ trợ tính năng có thể sinh thông điệp về việc không thể gọi `email()` do kết quả của `customer()` là `null`. Nội dung chính xác phụ thuộc vào bytecode/JVM/cấu hình, nên **không hardcode nguyên văn message để làm điều kiện kiểm thử**.

**Hai giới hạn quan trọng:**

- Nếu chương trình **tự tạo và ném** một NPE, chẳng hạn `throw new NullPointerException("customer required")`, hoặc `Objects.requireNonNull(customer, "customer")`, message đến từ **code chủ động tạo ngoại lệ**, không phải cơ chế phân tích dereference của Helpful NPE.
- Không phải mọi NPE đều có message chi tiết. Có thể do cấu hình runtime, môi trường, loại ngoại lệ hoặc thiếu thông tin thực thi cần thiết. **Ngay cả khi message giàu chi tiết, vẫn phải log Throwable** để giữ stack trace và cause.

Helpful NPE mặc định được bật trong những bản JDK hiện đại theo thay đổi từ Java 15; nhưng đây là công cụ hỗ trợ điều tra, **không thay thế validation**, **không bảo đảm mọi NPE đều dễ giải thích**, và cũng không nên công khai thông báo kỹ thuật nguyên văn cho người dùng cuối.

### Đừng để thông điệp NPE làm lộ thông tin nhạy cảm

Thông báo Helpful NPE có thể chứa **tên trường hoặc đường truy cập dữ liệu của code**, đôi khi cung cấp manh mối về cấu trúc nội bộ. Vì vậy:

- Log kỹ thuật phải có phân quyền/retention phù hợp và tránh ghi password, token, thông tin cá nhân hoặc dữ liệu khách hàng không cần thiết.
- Phản hồi HTTP/UI cho người dùng thường chỉ cần mã lỗi và thông điệp an toàn, còn chi tiết kỹ thuật được giữ ở hệ thống log kiểm soát truy cập.
- Không mặc định công bố `e.getMessage()` của NPE ra API response.
- Tránh nhồi toàn bộ object request hoặc dữ liệu thô vào log vì `toString()` của object có thể đưa thông tin nhạy cảm vào bản ghi.

**Lưu ý:** Logging ngoại lệ đầy đủ có thể chứa message, tên class, method và stack frames; đó chính là lý do cần chính sách bảo mật log phù hợp, chứ không phải lý do để xóa sạch trace khi chẩn đoán.

## 6. Đúng vị trí: ghi log một lần ở ranh giới xử lý

Một hệ thống có nhiều tầng, ví dụ `Controller → Service → Repository`. Nếu mỗi tầng đều:

```java
catch (RuntimeException e) {
    logger.log(Level.SEVERE, "failed", e);
    throw e;
}
```

thì **cùng một lỗi có thể bị ghi nhiều lần**, khiến bảng theo dõi nhiễu, số lượng lỗi bị đếm sai và chi phí lưu trữ tăng. Đoạn này không sai về mặt lưu giữ trace, nhưng thường **không phải chiến lược log tốt** khi các tầng chỉ chuyển tiếp cùng một lỗi.

Quy ước thực tế:

1. **Tầng thấp** phát hiện lỗi và có thể thêm ngữ cảnh qua exception chaining, nếu thật sự cần.
2. **Tầng trung gian** chỉ bắt khi có thể khôi phục, chuyển đổi lỗi có chủ đích hoặc bổ sung thông tin; nếu không thì để lỗi lan truyền.
3. **Tầng ranh giới** (worker consumer, scheduled job, request handler, message listener) ghi một lần với **`Throwable` đầy đủ** và mã ngữ cảnh an toàn như `requestId` hay `correlationId`.
4. **Bộ xử lý phản hồi** trả thông báo an toàn cho client; không trả stack trace ra ngoài chỉ vì log đã có nó.
5. **Cấu hình logging** quyết định level, log destination, retention và sampling nếu cần.

**Không bắt toàn bộ NPE một cách máy móc** chỉ để chuyển nó thành lỗi nghiệp vụ: NPE thường biểu thị lỗi lập trình hoặc vi phạm hợp đồng dữ liệu. Với dữ liệu đầu vào có thể thiếu, nên kiểm tra bằng `Objects.requireNonNull`, kiểm tra domain hoặc validation API ở ranh giới thích hợp. Ví dụ demo cố ý bắt NPE để minh họa **cách giữ cause**, không phải gợi ý rằng mọi service phải bắt `NullPointerException`.

### Phân biệt những tình huống nghiệp vụ

| Tình huống | Hướng xử lý thường hợp lý |
| --- | --- |
| Đầu vào bắt buộc bị `null` | Validate ở ranh giới, trả lỗi input rõ ràng; log theo mức phù hợp |
| NPE bất ngờ trong code | Giữ stack trace và cause, ghi log có ngữ cảnh; sửa nguyên nhân |
| Ngoại lệ thấp tầng cần biểu diễn bằng lỗi domain | Tạo exception mới với `(message, cause)` |
| Ngoại lệ có thể khôi phục ngay tại chỗ | Xử lý và log nếu cần, tránh báo `SEVERE` cho một tình huống bình thường |
| Lỗi đi qua nhiều tầng mà không đổi ý nghĩa | Để lan truyền, hạn chế log trùng |
| Lỗi xảy ra đồng thời trong thân `try` và khi đóng tài nguyên | Giữ cả lỗi chính và `getSuppressed()` |
| Lỗi ghi nhận vào system log không xuất hiện | Kiểm tra logger/handler level, filter, formatter và cấu hình vận hành trước khi kết luận không có exception |

## 7. Kiểm tra ngoại lệ trong log thay vì chỉ kiểm tra chuỗi

Nếu dùng JUL, đơn vị kiểm chứng thích hợp là `LogRecord`, đặc biệt:

```java
LogRecord record = ...; // Nhận từ Handler test.
Throwable exception = record.getThrown();
```

Đoạn này là **snippet**, không phải chương trình độc lập. Với handler thu log như ví dụ chính, có thể kiểm tra:

```java
// Các biến record và expectedException phải được khai báo trong test.
if (record.getThrown() != expectedException) {
    throw new AssertionError("Không log đúng Throwable");
}
```

Kiểm tra danh tính `Throwable` thông qua `==` đặc biệt hữu ích trong test: nó xác nhận logging không chỉ dựng một chuỗi hoặc tạo một exception mới không liên quan.

### Các thuộc tính cần kiểm thử

| Thuộc tính | Test nên kiểm tra | Lý do |
| --- | --- | --- |
| Mức log | `record.getLevel() == Level.SEVERE` hoặc mức mong muốn | Tầng giám sát phân loại được mức nghiêm trọng |
| Thông điệp ngữ cảnh | `record.getMessage()` có mã request/job an toàn | Xác định hoạt động bị lỗi |
| Throwable | `record.getThrown() == exception` | Ngăn việc mất object ngoại lệ |
| Cause | `record.getThrown().getCause() == root` | Chứng minh nguyên nhân gốc không bị mất khi bọc |
| Kiểu nguyên nhân | `root instanceof NullPointerException` | Phân biệt NPE với lỗi chuyển đổi ở tầng cao |
| Stack trace | Có frame liên quan trong `root.getStackTrace()` (nếu môi trường bảo đảm) | Xác nhận đường đi về method phát sinh lỗi |
| Suppressed | Kiểm tra `getSuppressed()` khi có `try-with-resources` | Không mất các lỗi phụ liên quan |
| An toàn nội dung | Message không có mật khẩu/token/dữ liệu nhạy cảm | Phù hợp chính sách log |

**Không nên** assert cả chuỗi stack trace giống hệt một bản snapshot theo mọi JDK: tên class, line number, đường dẫn, format và số frame có thể thay đổi. Các bài test ổn định hơn khi kiểm tra **tham chiếu throwable, kiểu cause và cấu trúc chuỗi nguyên nhân**, kết hợp kiểm tra frame trong môi trường biết chắc.

### Kiểm tra formatter khi cần xuất log dạng text

Với Java standard logging, `SimpleFormatter` hoặc formatter được cấu hình sẽ quyết định dạng văn bản. Nếu yêu cầu hệ thống là log phải chứa dòng `Caused by`/`Suppressed`, nên có **integration test** cho handler + formatter đã dùng thật, thay vì chỉ kiểm tra `getThrown()`.

`Throwable.printStackTrace(PrintWriter)` có thể tạo một bản text của stack trace khi thật sự cần xuất định dạng thủ công. Nhưng trong logging thông thường, không nên tự nối `printStackTrace` thành `String` rồi lại truyền vào logger: dễ phát sinh format trùng, lẫn byte/encoding, và khiến log không còn trường Throwable riêng để hệ thống giám sát trích xuất.

## 8. Đừng làm mất thông tin khi rethrow hoặc wrap

Có bốn tình huống đáng phân biệt:

### 8.1. Chỉ truyền lại

```java
catch (RuntimeException e) {
    throw e;
}
```

Cùng một đối tượng ngoại lệ tiếp tục được ném. **Không có exception mới**. Nếu không cần xử lý, có thể bỏ cả khối catch để mã ngắn hơn.

### 8.2. Bọc ngoại lệ và giữ cause

```java
catch (RuntimeException e) {
    throw new IllegalStateException(
            "Không thể hoàn tất xử lý R-7", e);
}
```

Tạo ngoại lệ mới tại nơi bọc, nhưng `getCause()` giữ `e` và trace của nó. Đây là lựa chọn hợp lý khi tầng nghiệp vụ cần chuyển loại hoặc bổ sung ngữ cảnh.

### 8.3. Bọc ngoại lệ nhưng làm mất cause

```java
catch (RuntimeException e) {
    // Không nên nếu cần giữ nguyên nhân gốc:
    throw new IllegalStateException(
            "Không thể hoàn tất xử lý R-7");
}
```

Bản mới không liên kết với `e`. Nếu sau đó chỉ log bản mới thì stack trace gốc ở vị trí phát sinh NPE khó truy ra từ log.

### 8.4. Chỉ log message, rồi che lỗi

```java
catch (NullPointerException e) {
    logger.warning("Thiếu dữ liệu: " + e.getMessage());
    return "";
}
```

Có thể làm mất stack trace, che lỗi lập trình và khiến hàm trả về chuỗi trống như một giá trị hợp lệ giả. Chỉ xử lý tiếp tục khi đó là **hợp đồng lỗi thực sự được thiết kế**, có chiến lược khôi phục/giá trị dự phòng rõ ràng và test đầy đủ.

## 9. Giải thích sâu hơn về cause và suppressed

**Cause** và **suppressed** không giống nhau:

- **Cause:** ngoại lệ nằm bên dưới để giải thích *vì sao* ngoại lệ hiện tại tồn tại. Chuỗi có thể nhiều tầng: `ProcessingException → DataAccessException → NullPointerException`.
- **Suppressed:** một hoặc nhiều ngoại lệ khác được ghi nhận *đồng thời* với ngoại lệ chính, nhưng không thay thế ngoại lệ chính; thường do resource cleanup trong `try-with-resources`.
- **Stack trace:** các frame liên quan tới bản thân **mỗi Throwable**, không phải một danh sách frame hợp nhất tự động.

Ví dụ sơ đồ:

```text
ProcessingException
    stack trace: process(...), handler(...)
    cause  ──> NullPointerException
                   stack trace: extractEmail(...), process(...), ...
    suppressed: (nếu bản thân ngoại lệ này có)

IllegalStateException("primary-failed")
    stack trace: resourceFailure(...), ...
    suppressed ──> IllegalStateException("close-failed")
                      stack trace: FailClose.close(...), ...
```

Một logger nhận **đúng ngoại lệ gốc hoặc bao ngoài** có thể cung cấp dữ liệu để formatter thể hiện cả hai loại quan hệ. Nếu chỉ ghi message hoặc chỉ chọn phần tử đầu của `getStackTrace()`, phần còn lại bị mất.

**Đừng tự viết đoạn code “lấy root cause cuối rồi chỉ log nó” làm mặc định.** Root cause hữu ích, nhưng **ngoại lệ bao ngoài** có thể giữ ngữ cảnh nghiệp vụ rất quan trọng. Hãy log ngoại lệ đầy đủ; công cụ phân tích có thể truy vết cause chain từ chính đối tượng đó.

## 10. Lưu ý mức log, tính năng bật/tắt và dữ liệu vận hành

- **`Level.SEVERE`** dành cho thất bại nghiêm trọng; không mặc định dùng cho mọi lỗi được dự đoán. Nếu không thể xử lý một request nhưng hệ thống vẫn chạy, lựa chọn level theo chính sách vận hành và mức quan trọng của sự kiện.
- **`Level.WARNING`** có thể phù hợp với vấn đề đáng chú ý nhưng chưa làm ngừng hoạt động, ví dụ lỗi cleanup có thể khôi phục. Level cụ thể phụ thuộc chính sách hệ thống.
- **Handler filter và level:** gọi `Logger.log(...)` không bảo đảm có dòng log được ghi ra tệp; handler có thể lọc.
- **Đồng thời và async:** trong hệ thống đa luồng, logging có thể được đẩy sang queue/handler khác. Tránh sử dụng handler tự chế không thread-safe để kết luận cho production.
- **Log context:** ưu tiên ID an toàn có thể đối chiếu (`requestId`, `traceId`, `jobId`), loại sự kiện và thao tác thất bại; không cần ghi toàn bộ request payload.
- **PII và bí mật:** không log password, token, API key hay thông tin cá nhân nhạy cảm. Giới hạn quyền xem, retention và việc xuất log ra hệ thống bên thứ ba.
- **Format có cấu trúc:** ứng dụng có thể dùng logger/framework khác hoặc JSON logs; nguyên tắc vẫn là **giữ exception/stack/cause dưới dạng dữ liệu được logger hỗ trợ**, thay vì biến mọi thứ thành một chuỗi `getMessage()`.

Nếu thư viện logging của dự án không phải JUL, hãy dùng **overload nhận exception/throwable đúng theo API của thư viện đó**. Đặc biệt chú ý sự khác nhau giữa tham số dùng để *format message* và tham số ngoại lệ dùng để *gắn stack trace*. Không giả định mọi overload có cùng thứ tự tham số.

## 11. Các lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| Chỉ ghi `e.getMessage()` | Không đính kèm Throwable; mất stack/cause trong log record | `logger.log(Level.SEVERE, context, e)` |
| Chỉ ghi `e.toString()` | Chỉ có tên exception + message, không có các frame | Truyền trực tiếp Throwable |
| Bọc ngoại lệ mới nhưng bỏ `cause` | Mất đường dẫn đến nơi NPE ban đầu | `new DomainException(message, e)` |
| Log từng tầng rồi ném lại cùng exception | Trùng log, nhiễu giám sát | Log ở ranh giới có trách nhiệm xử lý |
| Ghi chỉ `e.getCause()` | Có thể mất stack và ngữ cảnh của wrapper | Log wrapper có đủ cause chain |
| Cố định nguyên văn Helpful NPE message trong test | Test dễ vỡ giữa JDK/cấu hình | Test kiểu cause, điều kiện và frame quan trọng |
| Coi `getMessage()` luôn khác `null` | Log có thể ghi `null` hoặc thông tin rất ít | Không dựa riêng vào message |
| Bắt `NullPointerException` để trả giá trị mặc định dù lỗi bất ngờ | Che bug và làm state khó truy vết | Validate input, chỉ recover khi có hợp đồng |
| Gọi `fillInStackTrace()` trước khi ghi log | Có thể làm thay đổi trace của ngoại lệ | Giữ Throwable gốc |
| Chỉ nhìn `getCause()`, bỏ `getSuppressed()` | Có thể thiếu lỗi cleanup đi kèm | Ghi Throwable đầy đủ |
| Dựa vào số dòng trace/timestamp để viết test | Test bị phụ thuộc môi trường | Kiểm tra `LogRecord.getThrown()` và chuỗi cause |
| Log dữ liệu khách hàng hoặc secret cùng exception | Rò rỉ thông tin ở log | Chỉ log ID/ngữ cảnh an toàn, bảo vệ log |

## 12. Checklist thực hành trước khi đưa vào hệ thống

1. **Xác định điểm lỗi:** có phải NPE bất ngờ hay dữ liệu đầu vào không hợp lệ cần validation?
2. **Không đánh mất cause:** nếu bọc ngoại lệ, gọi constructor `(message, cause)`; nếu chỉ chuyển tiếp, ném lại cùng object hoặc không catch.
3. **Ghi log ở ranh giới phù hợp**, tránh log lặp tại mọi tầng.
4. **Dùng overload nhận `Throwable`**, ví dụ JUL `logger.log(Level.SEVERE, message, e)`.
5. **Thêm ngữ cảnh tác vụ an toàn**: request/job/correlation ID không nhạy cảm và hành động đang làm.
6. **Kiểm tra cấp log và handler**: logger bật chưa, level/filter cho phép chưa, formatter có hiển thị Throwable chưa?
7. **Kiểm thử cause chain:** wrapper có đúng `getCause()` và cause còn stack frame ban đầu hay không.
8. **Kiểm thử suppressed:** nếu dùng `try-with-resources`, xem những lỗi xảy ra lúc đóng tài nguyên có được giữ lại không.
9. **Không hardcode thông báo Helpful NPE:** nội dung có thể đổi; test logic và đối tượng ngoại lệ thay vì string message chi tiết.
10. **Giữ bí mật và kiểm soát quyền đọc log:** tránh dữ liệu cá nhân và thông tin nội bộ không cần thiết.

### Câu hỏi tự kiểm tra

**1.** Vì sao `logger.severe(e.getMessage())` không đủ để debug NPE?

Vì nó chỉ truyền **String message**; logger không có đối tượng `Throwable` để truy cập stack trace, cause hoặc suppressed.

**2.** Khi chuyển `NullPointerException` thành `ProcessingException`, nên viết gì?

Dùng constructor nhận **`(message, cause)`**, chẳng hạn `new ProcessingException("Lỗi xử lý", npe)`, để ngoại lệ mới giữ tham chiếu đến NPE gốc.

**3.** `throw e;` có tự tạo exception mới không?

Không. Nó ném lại cùng đối tượng `e`. Nếu không cần xử lý ở tầng trung gian, có thể để ngoại lệ lan truyền trực tiếp.

**4.** Tại sao không nên chỉ log `exception.getCause()`?

Vì cause có thể thiếu ngữ cảnh bổ sung và stack trace của **wrapper**. Log exception bao ngoài với cause chain còn nguyên thường giàu thông tin hơn.

**5.** Khi `try-with-resources` gặp lỗi chính và lỗi `close()`, lỗi `close()` ở đâu?

Thông thường nó được gắn vào **`getSuppressed()` của ngoại lệ chính**. Log đúng đối tượng Throwable giúp giữ thông tin đó.

**6.** Helpful NPE có thay thế stack trace không?

Không. Message chi tiết chỉ hỗ trợ giải thích biểu thức gây null; vẫn cần stack trace, cause và ngữ cảnh để điều tra.

## 13. Nguồn chính thức còn áp dụng

- [Oracle Java 25 API — `java.util.logging.Logger`](https://docs.oracle.com/en/java/javase/25/docs/api/java.logging/java/util/logging/Logger.html): overload `log(Level, String, Throwable)` và quá trình tạo `LogRecord`.
- [Oracle Java 25 API — `java.util.logging.LogRecord`](https://docs.oracle.com/en/java/javase/25/docs/api/java.logging/java/util/logging/LogRecord.html): trường `getThrown()`, level và message.
- [Oracle Java 25 API — `java.lang.Throwable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `getStackTrace()`, `getSuppressed()`, `printStackTrace()`.
- [OpenJDK JEP 358 — Helpful NullPointerExceptions](https://openjdk.org/jeps/358): cơ chế thông báo NPE chi tiết từ Java 14.
- [Oracle JDK 15 Release Notes](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html): Helpful NPE mặc định bật trong JDK 15.

**Ghi nhớ:** Để không đánh mất manh mối chẩn đoán null, hãy **giữ `Throwable` trong log**, **giữ cause khi bọc lỗi** và **không che stack trace bằng cách chỉ ghi message**. Thông điệp NPE có thể hữu ích, nhưng **stack trace + cause + ngữ cảnh nghiệp vụ an toàn** mới giúp tìm nguyên nhân và sửa lỗi có căn cứ.
