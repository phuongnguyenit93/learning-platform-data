# Ghi cả đối tượng ngoại lệ thay vì chỉ ghi `getMessage()` trong Java

Khi một thao tác Java thất bại, câu lệnh `logger.error("Lỗi: {}", exception.getMessage())` có thể tạo ra một dòng log trông có vẻ đủ thông tin. Nhưng khi cần biết lỗi phát sinh từ dòng mã nào, lời gọi nào dẫn đến lỗi hoặc có ngoại lệ nào nằm bên trong, thông điệp đơn lẻ thường không đủ. **Ghi đối tượng `Throwable` vào logger** giúp hệ thống lưu cả loại ngoại lệ, stack trace, chuỗi nguyên nhân (`cause`) và các ngoại lệ đi kèm (`suppressed exception`) mà formatter hỗ trợ.

Chủ đề này thuộc kỹ năng chẩn đoán và ghi log lỗi. Mục tiêu là phân biệt dữ liệu do `getMessage()` trả về với dữ liệu của toàn bộ ngoại lệ, dùng đúng API logging trong Java, giữ được nguyên nhân khi bọc/ném lại lỗi, và tránh tạo log nhiễu hoặc rò rỉ thông tin.

## 1. `Throwable` thực sự chứa những gì?

Trong Java, `Exception` và `Error` đều kế thừa `Throwable`. Một đối tượng `Throwable` có thể mang nhiều phần dữ liệu:

| Thành phần | Cách truy cập | Ý nghĩa |
| --- | --- | --- |
| Kiểu ngoại lệ | `exception.getClass()` | Xác định nhóm lỗi: `IOException`, `IllegalStateException`, `NumberFormatException`... |
| Thông điệp | `exception.getMessage()` | Mô tả ngắn do nơi tạo ngoại lệ cung cấp; **có thể là `null`** |
| Dòng mô tả | `exception.toString()` | Thông thường là tên lớp ngoại lệ kèm thông điệp nếu có |
| Ngăn xếp lời gọi | `exception.getStackTrace()` | Các khung stack liên quan tới lúc stack trace của ngoại lệ được tạo/điền |
| Nguyên nhân | `exception.getCause()` | Ngoại lệ bên dưới đã dẫn đến ngoại lệ hiện tại, nếu được liên kết |
| Ngoại lệ bị đính kèm | `exception.getSuppressed()` | Các ngoại lệ bổ sung, thường xuất hiện khi đóng tài nguyên bằng `try-with-resources` |

`getMessage()` **chỉ lấy một chuỗi**. Nó không thể tự mang stack trace, tên lớp ngoại lệ, chuỗi cause và suppressed exceptions. Ngay cả khi thông điệp ghi “Không đọc được hóa đơn”, ta vẫn cần biết thao tác đã lỗi tại đâu và nguyên nhân gốc là mất kết nối, quyền truy cập hay dữ liệu không hợp lệ.

Ví dụ:

```java
java.io.IOException root = new java.io.IOException("disk unavailable");
IllegalStateException error =
        new IllegalStateException("cannot load invoice 42", root);

System.out.println(error.getMessage());
System.out.println(error.getCause().getClass().getSimpleName());
```

Kết quả:

```text
cannot load invoice 42
IOException
```

Đây là **đoạn mã minh họa đặt trong phương thức**, không phải một chương trình Java độc lập. Hai dòng kết quả cho thấy: thông điệp của lỗi bên ngoài **không tự chứa** nguyên nhân `IOException`; người chẩn đoán phải theo `getCause()` hoặc dùng một formatter nhận cả `Throwable`.

## 2. So sánh: chỉ log thông điệp và log toàn bộ ngoại lệ

Trong ứng dụng dùng thư viện SLF4J (ví dụ SLF4J kết nối với Logback), so sánh:

```java
try {
    loadInvoice(invoiceId);
} catch (Exception exception) {
    logger.error("Cannot load invoice {}: {}",
            invoiceId, exception.getMessage()); // Thiếu Throwable.
}
```

với:

```java
try {
    loadInvoice(invoiceId);
} catch (Exception exception) {
    logger.error("Cannot load invoice {}", invoiceId, exception);
}
```

Hai khối trên là **mã minh họa bên trong ứng dụng** đã có `logger`, `invoiceId` và `loadInvoice(...)`, không thể chạy độc lập nếu chưa có những khai báo đó cùng thư viện SLF4J. Cú pháp `{}` là cơ chế tham số hóa thông điệp của SLF4J, **không phải** cú pháp `java.util.logging`.

Ở đoạn đầu, logger chỉ nhận chuỗi từ `exception.getMessage()`: thường mất tên loại ngoại lệ, các khung stack và nguyên nhân bên trong. Ở đoạn sau, logger nhận `Throwable` như một đối số ngoại lệ; với backend logging được cấu hình ghi lỗi, bản ghi có thể bao gồm stack trace và chuỗi cause.

Nếu không có tham số nghiệp vụ, cách rõ ràng nhất thường là:

```java
logger.error("Cannot load invoice", exception);
```

Ở đây tham số thứ hai là `Throwable`, thể hiện trực tiếp ý định ghi ngoại lệ. Với dạng có `{}`, hãy dùng đúng hợp đồng thư viện; trong SLF4J thông dụng, `Throwable` ở vị trí cuối của lời gọi tham số hóa được nhận diện là đối số ngoại lệ. Đừng cố bắt formatter đoán lỗi qua một chuỗi đã được chuyển đổi.

## 3. Ví dụ Java 17+ độc lập: logger nhận được cả `Throwable`

Java chuẩn đã có `java.util.logging` (JUL), không cần thêm thư viện. Ví dụ sau tạo handler nhỏ để in ra các trường đã nhận theo định dạng **cố định**, giúp kiểm tra không phụ thuộc timestamp hay mẫu formatter của môi trường. Trong ứng dụng thật, dùng handler/backend logging đã được cấu hình; phần handler thử nghiệm ở đây chỉ phục vụ quan sát.

Tạo tệp **`ExceptionLoggingDemo.java`**:

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ExceptionLoggingDemo {
    static void readInvoice() throws IOException {
        throw new IOException("disk unavailable");
    }

    static void processInvoice() {
        try {
            readInvoice();
        } catch (IOException cause) {
            throw new IllegalStateException("cannot load invoice 42", cause);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.exception.logging");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        Handler demoHandler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                Throwable error = record.getThrown();
                StringWriter buffer = new StringWriter();

                if (error != null) {
                    error.printStackTrace(new PrintWriter(buffer));
                }

                String trace = buffer.toString();
                System.out.println("level=" + record.getLevel());
                System.out.println("logMessage=" + record.getMessage());
                System.out.println("throwableAttached=" + (error != null));
                System.out.println("originInTrace="
                        + trace.contains("at ExceptionLoggingDemo.readInvoice("));
                System.out.println("causeInTrace=" + trace.contains(
                        "Caused by: java.io.IOException: disk unavailable"));
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };

        demoHandler.setLevel(Level.ALL);
        logger.addHandler(demoHandler);

        try {
            processInvoice();
        } catch (IllegalStateException exception) {
            System.out.println("onlyMessage=" + exception.getMessage());
            logger.log(Level.SEVERE, "Invoice processing failed", exception);
        } finally {
            logger.removeHandler(demoHandler);
            demoHandler.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ExceptionLoggingDemo.java
java ExceptionLoggingDemo
```

Đầu ra:

```text
onlyMessage=cannot load invoice 42
level=SEVERE
logMessage=Invoice processing failed
throwableAttached=true
originInTrace=true
causeInTrace=true
```

Giải thích:

1. `readInvoice()` ném `IOException("disk unavailable")`. `processInvoice()` bọc lỗi thành `IllegalStateException` kèm thông tin nghiệp vụ, **vẫn giữ nguyên nhân** qua constructor có đối số `cause`.
2. `exception.getMessage()` chỉ cho biết `cannot load invoice 42`. Nếu ứng dụng chỉ ghi giá trị đó, log không có stack trace/cause kèm theo.
3. `logger.log(Level.SEVERE, "Invoice processing failed", exception)` sử dụng overload nhận `Throwable`. `LogRecord.getThrown()` trong handler trả về đúng đối tượng ngoại lệ được gắn vào bản ghi.
4. `Throwable.printStackTrace(...)` cho phép handler kiểm tra bản trình bày đầy đủ có khung gọi `readInvoice()` và dòng `Caused by: java.io.IOException: disk unavailable`. Hai giá trị `true` chứng minh điều đó mà không phụ thuộc số dòng hoặc timestamp.

Với JUL, cách viết thông thường có thể chỉ là:

```java
logger.log(Level.SEVERE, "Failed to process invoice", exception);
```

Đây là một dòng minh họa trong phạm vi đã có `java.util.logging.Logger logger` và biến `exception`. Khi dùng `java.util.logging`, thông điệp tham số hóa theo mẫu `{0}`, `{1}` của `MessageFormat`, khác với `{}` trong SLF4J. Ví dụ:

```java
logger.log(Level.SEVERE, "Invoice {0} failed", new Object[] {invoiceId});
```

Dòng cuối chỉ minh họa **tham số hóa thông điệp** trong JUL; lời gọi này **không tự gắn ngoại lệ**. Nếu cần cả dữ liệu nghiệp vụ và `Throwable`, có thể dựng một thông điệp an toàn rồi gọi overload ba tham số `(Level, String, Throwable)`, hoặc dùng cơ chế bản ghi có ngữ cảnh của nền tảng logging.

## 4. Vì sao `getMessage()` thường không đủ để chẩn đoán?

### 4.1. Thông điệp có thể rỗng hoặc thiếu ngữ cảnh

Không phải constructor nào của exception cũng được truyền thông điệp:

```java
RuntimeException failure = new RuntimeException();
System.out.println(failure.getMessage() == null);
System.out.println(failure.getClass().getSimpleName());
```

Kết quả:

```text
true
RuntimeException
```

Đây là đoạn minh họa trong một phương thức. Log chỉ ghi `failure.getMessage()` có thể ghi `null`, trong khi tên lớp và stack trace vẫn giúp nhận diện lỗi. Một số API còn sử dụng thông điệp chung chung như “request failed”; chỉ có stack trace và cause mới giúp tìm đường đi thực tế.

### 4.2. Thông điệp không cho biết vị trí sinh lỗi

Hai thao tác cùng ném `IllegalArgumentException("invalid id")` có thể phát sinh tại hai nhánh xử lý khác nhau. `getMessage()` của chúng giống hệt nhau, còn stack trace giúp chỉ ra các phương thức và dòng mã liên quan đến từng lần tạo/ném lỗi.

Lưu ý: stack trace thường gắn với lúc exception được tạo hoặc khi `fillInStackTrace()` được gọi; không nên nghĩ logger tự phát minh lại lịch sử lời gọi tại thời điểm ghi log. Một exception được dùng lại hoặc được tạo với việc ghi stack trace bị vô hiệu hóa có thể không chứa các khung mong đợi. Stack trace cũng có thể thiếu/được rút gọn vì tối ưu hóa JVM hoặc cấu hình thư viện.

### 4.3. Thông điệp không chứa chuỗi nguyên nhân

Một lỗi nghiệp vụ có thể chứa nhiều tầng:

```text
IllegalStateException: cannot load invoice 42
    caused by IOException: disk unavailable
        caused by FileNotFoundException: /data/invoices/42.json
```

Ví dụ là một **chuỗi nguyên nhân khái niệm**, không phải stdout từ chương trình trên. Nếu chỉ ghi thông điệp của ngoại lệ ngoài cùng, ta có thể bỏ qua phần quan trọng nhất ở tầng I/O. Khi ghi cả `Throwable`, formatter chuẩn thường trình bày các khối `Caused by:` và các khung stack liên quan.

Không nên luôn bỏ tất cả wrapper để chỉ ghi cause sâu nhất. Ngoại lệ ngoài cùng có thể mang **ngữ cảnh có ý nghĩa**, như tên thao tác hoặc quy tắc nghiệp vụ đã thất bại. Ghi cả chuỗi giúp giữ đồng thời ngữ cảnh nghiệp vụ và nguyên nhân kỹ thuật.

### 4.4. Lỗi đóng tài nguyên có thể nằm trong `getSuppressed()`

Trong `try-with-resources`, nếu thân `try` ném ngoại lệ và thao tác `close()` cũng ném, Java giữ lỗi từ thân `try` làm lỗi chính và thêm lỗi đóng tài nguyên vào danh sách suppressed exceptions. `getMessage()` của lỗi chính không trình bày sự kiện bổ sung ấy.

## 5. Ví dụ thứ hai: log đầy đủ giữ được suppressed exception

Tạo tệp **`SuppressedExceptionDemo.java`**:

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;

public class SuppressedExceptionDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void useResource() throws IOException {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IOException("read failed");
        }
    }

    public static void main(String[] args) {
        try {
            useResource();
        } catch (IOException exception) {
            System.out.println("onlyMessage=" + exception.getMessage());
            System.out.println("suppressedCount="
                    + exception.getSuppressed().length);

            StringWriter buffer = new StringWriter();
            exception.printStackTrace(new PrintWriter(buffer));
            String trace = buffer.toString();
            System.out.println("primaryInTrace="
                    + trace.contains("java.io.IOException: read failed"));
            System.out.println("suppressedInTrace=" + trace.contains(
                    "Suppressed: java.io.IOException: close failed"));
        }
    }
}
```

Chạy:

```bash
javac --release 17 SuppressedExceptionDemo.java
java SuppressedExceptionDemo
```

Đầu ra:

```text
onlyMessage=read failed
suppressedCount=1
primaryInTrace=true
suppressedInTrace=true
```

Lỗi `read failed` là ngoại lệ chính. Trong quá trình rời khỏi `try-with-resources`, `close()` ném thêm `close failed`; Java đính lỗi này vào ngoại lệ chính qua `addSuppressed` bên dưới cơ chế `try-with-resources`. Nếu chỉ log `getMessage()`, thông tin `close failed` biến mất khỏi bản ghi. Log toàn bộ `Throwable` bằng một backend hỗ trợ stack trace cho phép nhìn thấy cả hai.

`getSuppressed()` cũng có thể trống, và một số ngoại lệ có cơ chế suppression bị vô hiệu hóa. Không nên giả định mọi lỗi đóng tài nguyên luôn nằm ở suppressed: cách xử lý phụ thuộc cấu trúc `try`, tài nguyên và ngoại lệ nào được ném trước.

## 6. Đặt `Throwable` đúng vị trí ở các logging API

### 6.1. Java Util Logging (`java.util.logging`)

```java
logger.log(Level.SEVERE, "Cannot load customer", exception);
```

Đây là lựa chọn rõ ràng khi dùng JUL: đối số thứ ba là `Throwable`, được lưu trong `LogRecord`. Nếu muốn thay đổi thứ tự hoặc định dạng các trường, đó là trách nhiệm của formatter/handler.

Cần phân biệt với:

```java
logger.severe("Cannot load customer: " + exception.getMessage());
```

Đoạn thứ hai chỉ gửi một chuỗi tới JUL. Không có tham chiếu `Throwable` trong bản ghi nên formatter không thể suy ra stack trace hay cause.

### 6.2. SLF4J và backend như Logback

```java
logger.error("Cannot load customer {}", customerId, exception);
```

Đây là **đoạn mã minh họa** trong ứng dụng có SLF4J, logger và biến `customerId`. Trong cách dùng SLF4J thông thường, đối số cuối `Throwable` được gắn vào sự kiện logging, còn `{}` nhận `customerId`. Có thể dùng overload trực tiếp `logger.error("Cannot load customer", exception)` khi không cần tham số hóa.

Ngược lại:

```java
logger.error("Cannot load customer {}: {}",
        customerId, exception.getMessage());
```

Chỉ ghi thông điệp lỗi dưới dạng chuỗi; stack trace không đi cùng bản ghi.

Chú ý về API cụ thể: nhiều thư viện có overload khác nhau cho `String`, `Object`, varargs và `Throwable`. Nếu wrapper logging của dự án không nhận diện Throwable ở đối số cuối như SLF4J, hãy dùng overload hoặc trường `cause` đúng theo hợp đồng của wrapper đó. Không nên dựa vào cách một hàm tùy biến chuyển các đối số sang chuỗi.

### 6.3. `System.Logger` trong Java

Ngoài JUL, Java còn có `System.Logger`. Có thể viết:

```java
System.Logger log = System.getLogger("billing");
log.log(System.Logger.Level.ERROR, "Cannot load customer", exception);
```

Đây là đoạn minh họa có thể đặt trong một phương thức hoặc chương trình Java. Overload nhận `Throwable` giúp gửi thông tin ngoại lệ cho bộ ghi log của nền tảng. Cách trình bày cụ thể phụ thuộc cấu hình logging/provider.

Trong cả ba cách, nguyên tắc giống nhau: **chuyển chính đối tượng ngoại lệ vào API logging có hỗ trợ `Throwable`**; việc gọi `.getMessage()` trước khi log làm mất những trường thông tin chưa được chuyển đổi.

## 7. Giữ nguyên nhân khi bắt và ném lại ngoại lệ

Việc log đủ stack trace không cứu được chuỗi cause nếu mã đã làm mất nó trước đó.

Ví dụ **không nên làm**:

```java
try {
    repository.load(id);
} catch (java.io.IOException exception) {
    throw new IllegalStateException(exception.getMessage());
}
```

Đây là đoạn minh họa cần `repository` và `id`. Ngoại lệ mới không liên kết với `IOException` cũ. Logger nhận cả `IllegalStateException` sau này cũng không thể tái tạo nguyên nhân đã bị loại bỏ.

Thay bằng:

```java
try {
    repository.load(id);
} catch (java.io.IOException exception) {
    throw new IllegalStateException(
            "Cannot load record " + id, exception);
}
```

Constructor nhận `cause` giữ được ngoại lệ gốc, đồng thời thêm ngữ cảnh thao tác. Trong các trường hợp chỉ cần chuyển tiếp lỗi mà không thêm ý nghĩa, `throw exception;` có thể phù hợp hơn việc tạo wrapper mới.

**Tránh tạo wrapper vô ích ở mọi tầng.** Việc bọc chỉ có giá trị khi đổi tầng trừu tượng hoặc bổ sung thông tin cần thiết. Một chuỗi hàng chục `RuntimeException("failed", previous)` làm log khó đọc và khó nhóm lỗi, dù về kỹ thuật vẫn giữ cause.

## 8. Log tại ranh giới nào để tránh lặp và vẫn thấy lỗi?

Một exception có thể đi qua repository → service → controller → bộ xử lý lỗi toàn cục. Nếu mỗi tầng đều ghi `ERROR` cùng stack trace rồi ném tiếp, hệ thống có thể tạo nhiều bản ghi cho một sự cố. Điều này làm khó tìm nguyên nhân thực tế và tạo lưu lượng log lớn.

Một chiến lược thường dùng:

1. **Tầng thấp:** thêm ngữ cảnh rồi ném lại nếu lỗi không thể xử lý; chỉ log nếu tại đây có hành động phục hồi, quyết định nghiệp vụ hoặc thông tin chẩn đoán không thể bổ sung ở tầng cao.
2. **Tầng xử lý lỗi sở hữu quyết định cuối:** log `Throwable` **một lần** với mã yêu cầu/tên thao tác đủ để tìm lại, chuyển thành phản hồi hoặc trạng thái thất bại phù hợp.
3. **Tầng đã phục hồi được lỗi:** có thể ghi `WARN` cùng lý do fallback nếu cần theo dõi; không nhất thiết in toàn bộ stack trace cho một tình huống dự kiến xảy ra thường xuyên.
4. **Lỗi nghiêm trọng hoặc bất ngờ:** chuyển đủ nguyên nhân vào hệ thống giám sát, ưu tiên khả năng tìm stack trace và ngữ cảnh an toàn.

Không có một vị trí log `ERROR` duy nhất phù hợp cho mọi kiến trúc; điều quan trọng là **chủ sở hữu việc ghi log phải rõ**. Hãy cân nhắc log một lần tại ranh giới có đủ ngữ cảnh, thay vì log rồi ném lên vô hạn.

## 9. Ngoại lệ trong `CompletableFuture`, `ExecutorService` và callback

Với tác vụ bất đồng bộ, luồng gọi có thể nhận ngoại lệ **bọc** thay vì ngoại lệ gốc:

- `Future.get()` thường ném `ExecutionException`, `getCause()` chứa thất bại của tác vụ.
- `CompletableFuture.join()` thường ném `CompletionException`, `getCause()` chứa thất bại nguồn.
- Một callback `whenComplete((value, error) -> ...)` nhận `Throwable` khi stage thất bại; `error` có thể là ngoại lệ gốc hoặc lớp bọc kỹ thuật tùy pipeline.

Ví dụ minh họa một ranh giới log:

```java
try {
    future.join();
} catch (java.util.concurrent.CompletionException exception) {
    logger.error("Async invoice computation failed", exception);
    throw exception;
}
```

Đoạn này cần một `CompletableFuture<?> future` và `logger` của ứng dụng; sử dụng API `logger.error` theo SLF4J. Khi logger được truyền **cả `CompletionException`**, formatter có thể in chuỗi `Caused by:`. Nếu tầng xử lý muốn phân loại lỗi gốc, có thể gỡ `CompletionException`/`ExecutionException` để chọn chính sách, nhưng nên giữ chuỗi gốc trong log để biết đường đi qua future.

Một chương trình gọi `submit()` nhưng bỏ `Future` hoặc tạo `CompletableFuture` mà không có nơi quan sát lỗi có thể bỏ lỡ việc ghi log. Tác vụ thất bại không có nghĩa hệ thống tự động gọi logger. Thiết kế phải xác định **ai quan sát kết quả và chịu trách nhiệm xử lý lỗi**.

Trong callback `whenComplete`, nếu chỉ muốn quan sát, hãy tránh để chính câu lệnh log ném ngoại lệ mới. Callback bị lỗi có thể làm stage trả về thay đổi trạng thái. Với logger thông dụng, nguy cơ này hiếm, nhưng code tùy biến gọi mạng/I/O trong callback vẫn cần kiểm soát.

## 10. Đọc log đầy đủ để lần theo lỗi

Một bản ghi có stack trace kiểu:

```text
java.lang.IllegalStateException: cannot load invoice 42
    at ExceptionLoggingDemo.processInvoice(ExceptionLoggingDemo.java:...)
Caused by: java.io.IOException: disk unavailable
    at ExceptionLoggingDemo.readInvoice(ExceptionLoggingDemo.java:...)
```

Đây là **dạng minh họa**, dấu `...` chỉ số dòng phụ thuộc tệp nguồn chứ không phải stdout được cam kết. Khi phân tích:

- Dòng đầu mô tả **ngoại lệ đang được báo** tại ranh giới log.
- Các dòng `at ...` cho biết khung gọi liên quan đến stack trace. Kiểm tra khung đầu tiên thuộc mã ứng dụng, đồng thời xem đường dẫn gọi vào đó.
- `Caused by:` cho biết lỗi bên dưới được giữ bằng `getCause()`.
- `Suppressed:` nếu có, thường cho biết lỗi phụ như đóng tài nguyên.
- Phần `... N more` trong stack trace là cách Java rút gọn các khung trùng giữa cause và wrapper; không chứng minh dữ liệu nguyên nhân đã mất.

Đừng chỉ nhìn một dòng top-level và kết luận lỗi nằm ở controller, endpoint hoặc `join()`. Những vị trí đó có thể chỉ là nơi lỗi **được quan sát**, còn nguyên nhân ban đầu được tạo trong repository/worker ở một phần khác của chuỗi.

`exception.toString()` hữu ích hơn `getMessage()` khi cần cả tên lớp và thông điệp, nhưng **vẫn không thay thế** cho một log record đính kèm `Throwable`.

## 11. Nguyên tắc bảo mật, hiệu năng và chất lượng log

Log đầy đủ là công cụ chẩn đoán; cần dùng có trách nhiệm:

- **Không đưa bí mật vào thông điệp lỗi hoặc ngữ cảnh log.** Password, token truy cập, cookie, dữ liệu định danh nhạy cảm hoặc nội dung request tùy ý có thể bị ghi lại nếu ứng dụng lồng chúng vào exception message. Truyền cả `Throwable` không tự động ẩn các dữ liệu đó.
- **Giảm dữ liệu có tính cá nhân.** Dùng mã tương quan yêu cầu, mã nghiệp vụ không nhạy cảm và trạng thái lỗi đã được phép ghi. Nếu log tập trung có bộ lọc/masking, kiểm tra cả trường message và stack trace.
- **Không giả định logger sẽ luôn in stack trace.** Output phụ thuộc backend, formatter, cấu hình mức log, sampling và nơi lưu log. Cần kiểm tra cấu hình thực tế để xác nhận trường throwable được ghi.
- **Ưu tiên logging có tham số.** Với SLF4J, mẫu `logger.error("Failed order {}", orderId, exception)` giữ cấu trúc tham số và tránh nối chuỗi thông điệp thủ công. Chú ý API cụ thể của thư viện và cơ chế rút trích `Throwable`.
- **Giới hạn log lặp lại.** Một lỗi xảy ra hàng nghìn lần trong vòng lặp không nên vô điều kiện tạo hàng nghìn stack trace lớn. Cân nhắc cảnh báo theo lô, đếm metric, lấy mẫu hoặc giảm mức độ sau khi đã nhận diện sự cố.
- **Xử lý đúng mức độ lỗi.** `INFO`, `WARN`, `ERROR`/`SEVERE` nên phản ánh tác động và hành động cần thiết, không phải cứ có `Exception` là log mức cao nhất.
- **Không phụ thuộc `printStackTrace()` trực tiếp trên production.** Nó hữu ích khi học hoặc kiểm thử, nhưng ghi ra stderr không cung cấp đầy đủ định tuyến, mức log, mã tương quan và chính sách dữ liệu của nền tảng logging.
- **Không nuốt lỗi sau khi log.** Nếu phương thức không phục hồi được, hãy truyền lỗi hoặc trả kết quả thất bại phù hợp; ghi log rồi trả giá trị “thành công” không có giải thích khiến hệ thống khó phát hiện sai lệch.

## 12. Checklist chẩn đoán và câu hỏi tự kiểm tra

Khi gặp dòng “Failed to process” không rõ nguyên nhân, hãy kiểm tra:

1. Ở nhánh `catch`, hệ thống **đưa `Throwable` vào logger**, hay chỉ chuyển nó thành `getMessage()`/`toString()`?
2. Khi bọc lỗi, constructor **có nhận `cause`** không?
3. Trong log có tên loại ngoại lệ, stack trace, `Caused by:` và (nếu có) `Suppressed:` không?
4. Lỗi được log tại ranh giới sở hữu việc xử lý, hay bị ghi lặp lại ở nhiều tầng?
5. Với công việc bất đồng bộ, code **có giữ và kiểm tra `Future`/`CompletableFuture`**, hay lỗi bị bỏ qua?
6. Nội dung ghi log có chứa dữ liệu nhạy cảm hoặc tạo quá nhiều bản ghi trùng lặp không?

**Câu 1.** `exception.getMessage()` có thể là `null` không?  
**Trả lời:** Có. Nó chỉ là phần mô tả tùy chọn, không phải toàn bộ ngoại lệ.

**Câu 2.** `logger.error("Failed: {}", exception.getMessage())` có chắc lưu stack trace không?  
**Trả lời:** Không. Theo cách dùng SLF4J thông thường, logger chỉ nhận một chuỗi từ `getMessage()` trong trường hợp này.

**Câu 3.** Cách ghi với JUL để chuyển cả exception là gì?  
**Trả lời:** `logger.log(Level.SEVERE, "Operation failed", exception)`; overload này đặt `Throwable` vào `LogRecord`.

**Câu 4.** `throw new IllegalStateException(exception.getMessage())` có giữ cause không?  
**Trả lời:** Không. Dùng `new IllegalStateException("context", exception)` khi cần giữ nguyên nhân.

**Câu 5.** Vì sao `getSuppressed()` quan trọng?  
**Trả lời:** Nó có thể chứa lỗi phát sinh khi đóng tài nguyên, trong khi lỗi chính vẫn là ngoại lệ ném từ thân `try`.

**Câu 6.** Nên log full stack trace ở mọi tầng không?  
**Trả lời:** Không nhất thiết. Nên chọn ranh giới có đủ ngữ cảnh và trách nhiệm xử lý, tránh cùng một sự cố bị log lặp lại vô ích.

**Câu 7.** `toString()` có thay thế được log cả `Throwable` không?  
**Trả lời:** Không. `toString()` thông thường chứa tên lớp và thông điệp nhưng không mang toàn bộ stack trace/cause/suppressed dưới dạng một bản ghi lỗi đầy đủ.

Kết luận thực hành: **hãy truyền đối tượng ngoại lệ cho API logging có hỗ trợ `Throwable`**, giữ nguyên nhân khi bọc lỗi, và ghi ngữ cảnh thao tác an toàn. `getMessage()` có ích để trình bày một thông điệp ngắn, nhưng không đủ làm bằng chứng chẩn đoán khi lỗi cần được điều tra.