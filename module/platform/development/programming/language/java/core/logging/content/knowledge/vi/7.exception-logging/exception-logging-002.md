# Truyền exception đúng cách trong Java Logging

Khi Java gặp lỗi, thông điệp như `"Save failed"` thường không đủ để điều tra. Người vận hành cần biết thao tác nào thất bại, đối tượng nào bị ảnh hưởng và **ngoại lệ gốc xuất phát từ đâu**. Vì vậy, một nguyên tắc quan trọng của *exception logging* là **truyền đối tượng `Throwable` cho logging API đúng cách**, thay vì chỉ chép chuỗi `getMessage()` hay `toString()` vào message.

Bài này phân biệt việc *ghi exception vào log*, *ném/lan truyền exception* và *bọc exception nhưng giữ nguyên nhân*; giải thích cách gọi Java Util Logging (JUL), SLF4J và những lỗi API dễ gặp. Các ví dụ chạy độc lập dùng Java 17 và JUL có sẵn trong JDK; ví dụ SLF4J được đánh dấu là mã minh họa cần dependency.

## 1. Exception mang những thông tin gì?

Trong Java, `Exception` là một nhánh của `Throwable`. `Throwable` có thể chứa:

| Thành phần | Cách lấy | Ý nghĩa |
| --- | --- | --- |
| **Loại ngoại lệ** | `error.getClass()` | Phân loại lỗi, ví dụ `IOException`, `IllegalStateException`, `SQLException`. |
| **Message** | `error.getMessage()` | Diễn giải do mã hoặc thư viện tạo; có thể `null`, không phải toàn bộ thông tin chẩn đoán. |
| **Stack trace** | `error.getStackTrace()`, `error.printStackTrace(...)` | Dãy frame cho biết nơi exception được tạo/ném và đường đi xử lý đã ghi nhận. |
| **Cause** | `error.getCause()` | Ngoại lệ nền gây ra lỗi hiện tại, ví dụ lỗi I/O dẫn đến lỗi lưu đơn hàng. |
| **Suppressed exceptions** | `error.getSuppressed()` | Lỗi phụ được lưu trong một số tình huống, thường khi đóng tài nguyên trong `try-with-resources`. |
| **Thông tin nghiệp vụ** | Message/field do ứng dụng tạo, nằm ngoài `Throwable` nếu cần | Ví dụ `orderId`, `jobId`, `requestId`, `operation`, `errorCode`. |

**Cause** và **suppressed** không đồng nghĩa: cause biểu thị chuỗi nguyên nhân đã khai báo; suppressed lưu lỗi phụ đi kèm một lỗi chính. Các formatter chuẩn thường có thể in cả chuỗi cause lẫn suppressed exception khi nhận được đối tượng `Throwable`.

### Truyền exception khác với chỉ ghi message

Giả sử `IOException` có message `"Disk unavailable"`:

```java
// Ví dụ minh họa trong catch; giả sử LOG là java.util.logging.Logger.
catch (java.io.IOException ex) {
    LOG.severe("Could not save file: " + ex.getMessage());
}
```

Lệnh trên ghi **một chuỗi**, không truyền `Throwable` cho JUL. Bản ghi có thể mất stack trace và quan hệ cause, khiến khó xác định lỗi phát sinh ở file/method nào. Chuyển sang overload có tham số `Throwable`:

```java
// Ví dụ minh họa trong catch; LOG là java.util.logging.Logger.
catch (java.io.IOException ex) {
    LOG.log(
        java.util.logging.Level.SEVERE,
        "event=file.save_failed pathId=report-42",
        ex
    );
}
```

`Logger.log(Level, String, Throwable)` đặt `ex` vào trường `LogRecord.thrown`. Handler/formatter phù hợp có thể in stack trace và cause. Chuỗi message riêng mô tả ngữ cảnh nghiệp vụ. Việc chuyển đúng đối tượng không bảo đảm formatter hay hệ thống thu thập luôn hiển thị toàn bộ stack trace: cấu hình đầu ra vẫn phải được kiểm tra.

## 2. Ba thao tác khác nhau cần hiểu chính xác

| Thao tác | Ví dụ | Kết quả |
| --- | --- | --- |
| **Log exception** | `logger.log(Level.SEVERE, "Saving failed", ex)` | Tạo bản ghi mang thông điệp và `Throwable`. Không tự ném ngoại lệ và không tự khắc phục lỗi. |
| **Rethrow** (ném lại) | `throw ex;` | Lan truyền cùng đối tượng exception lên tầng gọi; không tự tạo log record. |
| **Wrap with cause** (bọc giữ nguyên nhân) | `throw new IllegalStateException("Cannot save order", ex);` | Tạo exception cấp ứng dụng với ngữ cảnh mới, giữ exception cũ ở `getCause()`. |
| **Handle/recover** | Chuyển sang nguồn dự phòng hoặc trả kết quả từ chối hợp lệ | Có thể không cần log lỗi nặng nếu kết quả cuối cùng đúng hợp đồng. |

Không nên gọi `logger.error(...)` (hoặc `logger.log(...)` trong JUL) rồi cho rằng exception đã được ném cho caller. Logging chỉ ghi nhận thông tin. Tương tự, `throw ex` không tự phát một log event.

### Bọc exception: giữ nguyên cause

Một service muốn chuyển chi tiết lỗi I/O sang ngoại lệ phù hợp tầng nghiệp vụ có thể viết:

```java
// Đoạn mã minh họa; saveToDisk() có thể ném IOException.
try {
    saveToDisk();
} catch (java.io.IOException ex) {
    throw new IllegalStateException("Cannot persist order", ex);
}
```

Ở đây `IllegalStateException` giữ `IOException` trong `getCause()`. Nếu tầng bên ngoài log `IllegalStateException` như `Throwable`, stack trace của cause có thể được hiển thị cùng exception bao ngoài.

**Cách sai dễ gặp:**

```java
// Không nên: đánh mất cause và stack trace gốc.
throw new IllegalStateException(ex.getMessage());
```

Tạo exception mới chỉ từ message không giữ quan hệ nguyên nhân. Nếu cần thay đổi loại exception, dùng constructor nhận cause (nếu API hỗ trợ) hoặc `initCause` khi được thiết kế phù hợp. Không tự gọi `fillInStackTrace()` chỉ để “làm sạch” lỗi, vì có thể làm mất dấu vết chẩn đoán cần thiết.

## 3. Cách truyền Throwable vào Java Util Logging (JUL)

JUL có sẵn trong Java, có thể dùng mà không thêm thư viện:

```java
import java.util.logging.Level;
import java.util.logging.Logger;

Logger logger = Logger.getLogger("demo.orders");

// Giả sử error là Throwable đã bắt được.
logger.log(Level.SEVERE, "event=order.persist_failed", error);
```

Đoạn trên là **minh họa**, chưa phải class chạy độc lập; biến `error` phải tồn tại trong ngữ cảnh bắt lỗi. Khi gọi đúng overload `log(Level, String, Throwable)`:

1. `Level.SEVERE` chỉ mức độ của lỗi cuối cùng trong ví dụ.
2. Message mang loại sự kiện/ngữ cảnh hữu ích cho người đọc.
3. `error` được giữ dưới dạng `Throwable` trong `LogRecord.getThrown()`.
4. Formatter quyết định có hiển thị stack trace, cause và suppressed exception hay không.

### Cẩn thận với overload có tham số và overload Throwable

JUL có các overload đáng chú ý:

| Lời gọi | Ý nghĩa |
| --- | --- |
| `logger.log(level, message)` | Ghi message; không kèm throwable. |
| `logger.log(level, message, (Throwable) error)` | Ghi message và đặt `error` vào trường thrown. |
| `logger.log(level, "Order {0} failed", (Object) orderId)` | Một tham số được formatter dùng để thay `{0}` (nếu formatter hỗ trợ). |
| `logger.log(level, "Order {0}, retry {1}", new Object[]{orderId, attempt})` | Nhiều tham số định dạng. |
| `logger.log(LogRecord record)` | Ghi một record đã chuẩn bị, có thể chứa *cả parameters lẫn thrown*. |

**Bẫy của Java overload resolution:** Nếu `ex` có kiểu `Throwable` hoặc subtype và bạn viết:

```java
// Không dùng cách này khi mục đích là thay {0} bằng exception:
logger.log(Level.SEVERE, "Failure caused by {0}", ex);
```

Java chọn overload nhận `Throwable` (cụ thể hơn `Object`). Vì vậy `ex` là throwable đính kèm, **không phải tham số format `{0}`**. Chuỗi `{0}` có thể còn nguyên trong message. Muốn log kèm exception, hãy viết message mô tả sự kiện rõ ràng và truyền `ex` như tham số `Throwable` cuối:

```java
logger.log(
    Level.SEVERE,
    "event=job.failed jobId=job-9",
    ex
);
```

Hai đoạn trên cũng là **đoạn minh họa** trong ngữ cảnh đã có `logger` và `ex`. Không nối nguyên chuỗi exception vào message rồi lại truyền cùng exception nếu việc đó tạo nội dung trùng lặp không cần thiết.

### Khi cần cả placeholder lẫn Throwable trong JUL

JUL không có overload `log(Level, String, Object[], Throwable)`. Có thể tạo `LogRecord` rõ ràng:

```java
// Ví dụ minh họa; giả sử logger, orderId và ex đã tồn tại.
java.util.logging.LogRecord record = new java.util.logging.LogRecord(
        java.util.logging.Level.SEVERE,
        "event=order.failed orderId={0} outcome={1}"
);
record.setParameters(new Object[]{orderId, "failed"});
record.setThrown(ex);
record.setLoggerName(logger.getName());
logger.log(record);
```

Một formatter gọi `formatMessage(record)` sẽ thay các placeholder `{0}` và `{1}` theo cách JUL hỗ trợ, đồng thời vẫn đọc được `record.getThrown()`. Trong ứng dụng có structured logging, nên dùng API field/attribute của framework để lưu `orderId` có cấu trúc và giữ `Throwable` riêng.

## 4. Cách truyền exception với SLF4J

SLF4J là **logging facade** thường dùng cùng Logback hoặc một provider khác. Mã Java dưới đây là **đoạn minh họa cần dependency SLF4J**, không thể biên dịch với JDK thuần:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    void save(String orderId) {
        try {
            persist(orderId);
        } catch (RuntimeException ex) {
            LOG.error(
                    "event=order.persist_failed orderId={}",
                    orderId,
                    ex
            );
            throw ex;
        }
    }

    void persist(String orderId) {
        throw new IllegalStateException("Storage unavailable");
    }
}
```

Cú pháp `{}` là quy ước tham số của SLF4J, **khác `{0}` trong JUL**. Với cách gọi trên, `orderId` thay placeholder, còn `ex` là đối tượng `Throwable` ở vị trí cuối, được SLF4J nhận diện là exception (với các overload/thực thi thông dụng).

Có thể dùng kiểu gọi rõ ràng không có tham số định dạng:

```java
LOG.error("event=order.persist_failed", ex);
```

Đây là overload `error(String, Throwable)`. Khi có placeholder, hãy truyền đủ giá trị dữ liệu **trước** exception cuối; tránh dùng một exception làm “tham số thay chuỗi” nếu bạn muốn stack trace.

Các trường hợp cần chú ý:

- `LOG.error("Failed orderId={}", orderId, ex)`: tham số nghiệp vụ `orderId` và throwable `ex` ở cuối; mục đích rõ ràng.
- `LOG.error("Failed", ex)`: hợp lệ, nhưng không có order ID; bổ sung ngữ cảnh nếu cần.
- `LOG.error("Failed: " + ex.getMessage())`: chỉ truyền chuỗi; không giữ exception trong event.
- `LOG.error("Failed: {}", ex)`: dễ gây hiểu nhầm do overload nhận `Throwable` và placeholder; nếu muốn ghi lỗi, dùng message cố định và truyền throwable đúng vị trí.
- `LOG.error("Failed orderId={} error={}", orderId, ex)`: có nguy cơ để thừa placeholder hoặc hiểu sai tham số vì throwable cuối được xử lý riêng; tốt nhất chỉ dùng placeholder cho dữ liệu thường và gắn throwable cuối cùng.

Trong SLF4J 2.x có fluent API (`atError()`, `setCause(...)`, `addKeyValue(...)`), hỗ trợ biểu diễn cause và các field rõ ràng khi provider tương thích. Quyết định dùng API nào phụ thuộc phiên bản và backend đang cấu hình; không trộn cú pháp SLF4J với JUL.

## 5. Ví dụ Java 17 chạy độc lập: giữ nguyên nhân và truyền exception vào logger

Chương trình sau mô phỏng lỗi lưu đơn hàng: tầng thấp phát sinh `IOException`, tầng nghiệp vụ **bọc ngoại lệ và giữ cause**, tầng ranh giới bắt `IllegalStateException` rồi log một lần với `Throwable`. Chương trình cố tình dùng formatter một dòng chỉ hiển thị loại exception và cause để stdout ổn định. **Trong hệ thống thật, formatter thường cần in cả stack trace**, không chỉ tóm tắt như ví dụ.

Lưu thành **`ExceptionPassingDemo.java`**:

```java
import java.io.IOException;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class ExceptionPassingDemo {
    private static final Logger LOG =
            Logger.getLogger(ExceptionPassingDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                StringBuilder line = new StringBuilder()
                        .append(record.getLevel().getName())
                        .append(' ')
                        .append(formatMessage(record));

                Throwable thrown = record.getThrown();
                if (thrown != null) {
                    line.append(" | thrown=")
                        .append(thrown.getClass().getSimpleName())
                        .append(": ")
                        .append(thrown.getMessage());

                    Throwable cause = thrown.getCause();
                    if (cause != null) {
                        line.append(" | cause=")
                            .append(cause.getClass().getSimpleName())
                            .append(": ")
                            .append(cause.getMessage());
                    }
                }
                return line.append(System.lineSeparator()).toString();
            }
        });
        output.setLevel(Level.ALL);
        LOG.addHandler(output);

        try {
            processOrder("ord-42");
        } catch (IllegalStateException failure) {
            // Log duy nhất tại ranh giới đã biết kết quả cuối cùng.
            LOG.log(
                    Level.SEVERE,
                    "event=order.persist_failed orderId=ord-42 outcome=failed",
                    failure
            );
        } finally {
            output.flush();
            LOG.removeHandler(output);
        }
    }

    private static void processOrder(String orderId) {
        try {
            persist(orderId);
        } catch (IOException cause) {
            // Chuyển tầng trừu tượng, nhưng giữ nguyên cause.
            throw new IllegalStateException(
                    "Cannot persist " + orderId,
                    cause
            );
        }
    }

    private static void persist(String orderId) throws IOException {
        throw new IOException("Storage unavailable");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ExceptionPassingDemo.java
java ExceptionPassingDemo
```

**Standard output chính xác** (một dòng; không tính dấu nhắc lệnh):

```text
SEVERE event=order.persist_failed orderId=ord-42 outcome=failed | thrown=IllegalStateException: Cannot persist ord-42 | cause=IOException: Storage unavailable
```

Giải thích theo đường đi:

1. `persist` ném `IOException("Storage unavailable")`, biểu thị lỗi của tầng lưu trữ.
2. `processOrder` bắt lỗi I/O và tạo `IllegalStateException("Cannot persist ord-42", cause)`. Nhờ truyền `cause`, lỗi gốc vẫn truy vết được.
3. `main` là ranh giới biết thao tác không hoàn tất, nên log ở `SEVERE` đúng một lần. Tham số thứ ba của `LOG.log(Level.SEVERE, message, failure)` là `Throwable`, không phải một chuỗi hay tham số placeholder.
4. `record.getThrown()` trong formatter nhận được `IllegalStateException`; `getCause()` dẫn về `IOException`. Điều này chứng minh exception đã được **đính vào record**, không chỉ chèn text vào message.
5. Formatter tùy chỉnh chủ động không in stack frames để output có thể dự đoán; thay nó bằng formatter xuất stack trace khi vận hành nếu cần điều tra. Nếu dùng `java.util.logging.SimpleFormatter` mặc định, đầu ra chứa thêm timestamp, source và stack trace, nên không trùng mẫu một dòng ở trên.
6. `output.flush()` đẩy dữ liệu trong `StreamHandler` ra `System.out`; `setUseParentHandlers(false)` tránh in trùng do handler cấp cha. Trong ứng dụng thật, handler thường được cấu hình lúc khởi động thay vì tạo khi xử lý từng request.

Ví dụ xử lý lỗi tại ranh giới `main` và kết thúc chương trình sau khi log; ứng dụng server thực tế cần trả kết quả lỗi đúng hợp đồng hoặc cho exception handler xử lý tiếp. Không được coi thao tác `log` là hành động phục hồi dữ liệu.

## 6. Khi nào nên log, khi nào chỉ truyền exception lên trên?

Một ngoại lệ có thể đi qua nhiều lớp:

```text
Repository
   |  throws IOException
   v
Service
   |  wraps IllegalStateException(cause)
   v
Controller / job runner
   |  knows final outcome
   v
Logs one failure event (with Throwable)
```

Mỗi lớp đều biết một phần ngữ cảnh, nhưng không lớp nào cũng phải ghi stack trace. Một chính sách phổ biến là **log một lần tại ranh giới chịu trách nhiệm về kết quả cuối cùng**:

- **Repository:** ném lỗi có ngữ cảnh kỹ thuật và không cần tự log nếu service/caller sẽ xử lý. Nếu thêm cause, cần giữ chuỗi nguyên nhân.
- **Service:** có thể chuyển một ngoại lệ hạ tầng thành lỗi phù hợp nghiệp vụ bằng constructor nhận cause; nên bổ sung mã lỗi hoặc context nếu cần.
- **Controller / job runner / message consumer:** biết request/job cuối cùng thành công, thất bại hay đã phục hồi. Ghi event có level phù hợp, thông điệp rõ ràng và `Throwable` khi cần.
- **Global exception handler:** nếu handler này đã log lỗi của request, tránh controller hoặc service cũng log toàn bộ stack trace rồi ném lại y nguyên.

**Không phải mọi exception đều cần `ERROR/SEVERE`.** Một lỗi input bị từ chối đúng hợp đồng có thể là kết quả bình thường; một lần timeout được retry và cuối cùng thành công có thể chỉ cần thông tin `DEBUG` hoặc `WARN` có điều kiện. Level phản ánh *hậu quả thực tế* của thao tác, không chỉ việc có exception.

### Log rồi throw: khi nào hợp lý?

Mẫu:

```java
catch (RuntimeException ex) {
    logger.log(Level.SEVERE, "event=job.failed", ex);
    throw ex;
}
```

là hợp lý **nếu tầng đó là nơi ghi nhận chính thức** và tầng phía trên chỉ truyền lỗi/không log lại. Nếu mỗi lớp đều làm như vậy, một lỗi gây nhiều log `SEVERE` trùng, làm khó điều tra và gây nhiễu cảnh báo. Khi tái ném cùng exception với `throw ex;`, đối tượng và stack trace gốc được giữ, không cần tự bọc thêm nếu không đổi mức trừu tượng hoặc thêm ngữ cảnh hữu ích.

Trong một số hệ thống, “log trước rồi rethrow” còn khiến log ghi `failed` trong khi tầng bên ngoài có thể thực hiện fallback thành công. Vì thế hãy lựa chọn level và vị trí log dựa trên phạm vi thao tác mà bạn thực sự biết kết quả.

## 7. Chuỗi cause, suppressed exception và lỗi bất đồng bộ

### Chuỗi cause

Một lỗi thường được bọc nhiều tầng:

```text
OrderProcessingException
   caused by -> IllegalStateException
                 caused by -> IOException
```

Khi truyền exception ngoài cùng cho logging framework có formatter stack trace phù hợp, các cause có thể xuất hiện dưới dạng các phần `Caused by: ...`. Nếu chỉ ghi `getMessage()` của exception ngoài, dấu vết về `IOException` có thể biến mất.

Tránh cố ép mọi lỗi về “root cause” rồi chỉ truyền root cause duy nhất, vì như vậy có thể mất message và stack trace của tầng nghiệp vụ, nơi biết thao tác nào thất bại. Thường nên giữ và log **đối tượng exception đại diện cho lỗi cuối cùng cùng toàn bộ cause chain**.

### Suppressed exception

`try-with-resources` có thể giữ một lỗi xảy ra khi đóng tài nguyên dưới dạng suppressed exception của lỗi chính. Ví dụ trong ngữ cảnh phù hợp:

```java
// Đoạn minh họa cách kiểm tra thông tin Throwable.
for (Throwable suppressed : error.getSuppressed()) {
    System.out.println(suppressed.getClass().getName());
}
```

Không cần tự in suppressed exception trong ứng dụng khi formatter chuẩn đã cung cấp stack trace đầy đủ; ví dụ chỉ để nhấn mạnh rằng ngoài `getCause()` còn có `getSuppressed()`. Truyền đúng `Throwable` giúp framework có cơ hội hiển thị cả thông tin này; việc thực sự hiển thị tùy formatter/collector.

### Bất đồng bộ

Với `Future.get()`, exception trong tác vụ có thể được bọc bởi `ExecutionException`. Với `CompletableFuture.join()`, có thể gặp `CompletionException`. Khi điều tra, xem `getCause()` để tìm nguyên nhân gốc của tác vụ. Không tự nối `getMessage()` của wrapper rồi bỏ đối tượng `Throwable`.

Đối với retry, một failure nội bộ không nhất thiết là kết quả cuối cùng. Ghi log kèm `attempt`, `maxAttempts` và `outcome` nếu cần, nhưng tránh ghi `ERROR` cho mọi lần thử khi retry được dự kiến; đánh giá khi toàn bộ thao tác kết thúc.

Với `InterruptedException`, cần tuân thủ hợp đồng hủy tác vụ: thường ném tiếp hoặc khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` khi không thể rethrow. Chỉ log mà nuốt interrupt có thể khiến xử lý hủy hoạt động sai.

## 8. Truyền exception có ngữ cảnh mà không lộ dữ liệu nhạy cảm

Thông tin exception thường chứa dữ liệu do thư viện hoặc hệ thống ngoài tạo ra. `getMessage()`, stack trace và cả cause có thể mang URL, query, đường dẫn, thông tin kết nối, định danh cá nhân hoặc payload. **Truyền Throwable đúng API không đồng nghĩa với an toàn để công bố toàn bộ nội dung**.

Khi thiết kế log exception:

1. Ghi tên operation và loại kết quả rõ ràng: `event=order.persist_failed`, `outcome=failed`, `errorCode=STORAGE_UNAVAILABLE`.
2. Chỉ thêm ID đã được cho phép: `orderId` hoặc `requestId` phù hợp; không dùng password, token hay cookie làm correlation ID.
3. Dùng mã lỗi ổn định thay vì dựa hoàn toàn vào text exception có thể thay đổi qua phiên bản.
4. Cân nhắc masking/redaction ở nguồn và hệ thống nhận, cùng phân quyền truy cập, retention và chính sách thu thập stack trace.
5. Tránh nối nguyên request body, SQL kèm giá trị nhạy cảm, header `Authorization` hoặc `ex.toString()` vào message nếu có nguy cơ lộ thông tin.
6. Nếu exception phát sinh từ dữ liệu đầu vào không đáng tin cậy, lưu ý ký tự xuống dòng và ký tự điều khiển có thể làm log text khó đọc hoặc bị giả mạo; dùng formatter/encoder thích hợp, không tự ghép JSON bằng chuỗi.

Đặc biệt, ghi `Throwable` vào log tập trung có thể xuất thông tin nội bộ qua stack trace. Đây là dữ liệu vận hành cần kiểm soát truy cập, không phải thông tin mặc định trả cho người dùng cuối. Response HTTP nên dùng mã lỗi/thông điệp được kiểm soát, không trả nguyên stack trace cho client.

## 9. Hiệu năng và định dạng exception

Việc tạo exception kèm stack trace, định dạng trace và ghi ra sink đều có chi phí. Khi lỗi xảy ra hàng nghìn lần/giây, việc log toàn bộ stack trace ở mỗi vòng lặp có thể tăng CPU, I/O và dung lượng.

Các cách cân nhắc:

- Chỉ phát log ở ranh giới có ý nghĩa, tránh trùng lặp cùng exception qua nhiều tầng.
- Đặt level theo ảnh hưởng; đưa chẩn đoán chi tiết ở mức phù hợp, chỉ bật khi cần.
- Không tạo chuỗi stack trace thủ công bằng `StringWriter` ở mọi code path nếu logger/backend đã có khả năng format `Throwable` và sẽ lọc level.
- Không bỏ stack trace của lỗi cuối cùng quan trọng chỉ để tiết kiệm dung lượng. Có thể dùng rate limit/sampling theo chính sách, nhưng cần giữ bằng chứng phù hợp.
- Trong hệ thống dùng asynchronous logging, tìm hiểu chính sách flush, hàng đợi và mất log khi process kết thúc đột ngột; việc gắn `Throwable` vào event không bảo đảm event đã được lưu bền vững.
- Khi dùng structured logging, giữ exception ở trường lỗi tiêu chuẩn do backend hỗ trợ; kiểm tra pipeline có lưu được stack trace nhiều dòng hoặc trường exception có cấu trúc hay không.

Lưu ý: thời điểm ghi log khác thời điểm lỗi được tạo; các thread/trace context của một tác vụ bất đồng bộ có thể cần được truyền riêng. `Throwable` tự nó không mang đầy đủ correlation ID hay transaction context.

## 10. Những lỗi truyền exception thường gặp và cách sửa

| Cách làm dễ sai | Vấn đề | Cách phù hợp hơn |
| --- | --- | --- |
| `logger.severe(ex.getMessage())` trong JUL | Chỉ còn text; không đính stack trace/cause vào record. | `logger.log(Level.SEVERE, "event=operation.failed", ex)`. |
| `logger.log(Level.SEVERE, "Failure {0}", ex)` trong JUL | Có thể chọn overload `Throwable`, nên `{0}` không được thay. | Dùng message không placeholder + Throwable hoặc tạo `LogRecord` chứa cả `parameters` và `thrown`. |
| `LOG.error("Failure: " + ex)` với SLF4J | Chỉ nối chuỗi exception; thường mất stack trace. | `LOG.error("event=operation.failed", ex)`. |
| `LOG.error("Failed id={}", ex)` với SLF4J | Dễ nhầm overload `Throwable` và placeholder, thiếu dữ liệu nghiệp vụ. | `LOG.error("Failed id={}", id, ex)`. |
| `throw new RuntimeException(ex.getMessage())` | Mất cause, khó lần theo lỗi gốc. | `throw new RuntimeException("Operation failed", ex)`. |
| `logger.log(Level.SEVERE, "...", ex.getCause())` | Có thể bỏ sót stack của wrapper và thông tin nghiệp vụ. | Thường log `ex` ngoài cùng để giữ toàn chuỗi cause. |
| `ex.printStackTrace()` trong mã nghiệp vụ | In ra stderr ngoài pipeline logging/level/context đã cấu hình. | Dùng logging API với `Throwable` và context. |
| Ghi stack trace ERROR ở mọi catch rồi rethrow | Nhiều log trùng cho một sự cố, khó phân loại hậu quả. | Chọn ranh giới chịu trách nhiệm và log một lần khi biết outcome. |
| Catch exception rồi chỉ log, sau đó trả success | Làm sai kết quả ứng dụng, mất tín hiệu lỗi cho caller. | Xử lý phục hồi thật sự hoặc ném/trả lỗi theo hợp đồng. |
| Ghi toàn bộ exception cho client | Lộ stack trace và thông tin nội bộ. | Log nội bộ có kiểm soát, trả error code/message an toàn. |

**Đừng coi mọi exception là sự cố `SEVERE`.** Ví dụ parse đầu vào sai nhưng ứng dụng trả `400 Bad Request` đúng hợp đồng có thể không cần stack trace ERROR; ngược lại lỗi lưu giao dịch dẫn đến mất kết quả cần được ghi nhận phù hợp. `Throwable` giúp điều tra nguyên nhân; **level phản ánh ý nghĩa vận hành**.

## 11. Checklist khi review exception logging

Trước khi chốt một lời gọi logger trong `catch` hoặc global exception handler, tự kiểm tra:

- Exception thực sự được truyền dưới dạng `Throwable`, hay chỉ được chuyển thành chuỗi?
- Lời gọi có đúng **overload của JUL/SLF4J** và đúng cú pháp placeholder của thư viện không?
- Khi bọc ngoại lệ, constructor có nhận `cause` để giữ chuỗi nguyên nhân không?
- Đối tượng được log là exception ngoài cùng có chứa ngữ cảnh hữu ích không? Có vô tình bỏ mất cause/suppressed không?
- Message có cho biết **event, operation, đối tượng cần thiết, outcome và mã lỗi** mà không lộ bí mật không?
- Có đang log lặp lại cùng một lỗi ở nhiều tầng, hoặc log error khi còn retry/fallback có thể thành công không?
- Level có phản ánh hậu quả cuối cùng không, và logger/handler/appender có thực sự cho phép ghi sự kiện này không?
- Formatter và hệ thống tập trung có hiển thị/thu thập được stack trace, cause và các trường context như dự kiến không?
- Ở trường hợp phục hồi, code có thực sự xử lý lỗi? Ở trường hợp thất bại, ngoại lệ hoặc trạng thái lỗi có được truyền đến nơi chịu trách nhiệm không?
- Nội dung exception/stack trace có đi qua kiểm soát truy cập, lọc dữ liệu nhạy cảm và retention đúng chính sách không?

**Nguyên tắc cốt lõi:** Truyền `Throwable` vào logger bằng đúng API để giữ dấu vết kỹ thuật; truyền hoặc bọc exception trong code bằng `throw` và cause để giữ lỗi xuyên các tầng; và chỉ ghi sự kiện thất bại ở nơi có đủ thông tin về kết quả. Message mô tả *điều gì thất bại*, còn exception giúp tìm *vì sao thất bại*.