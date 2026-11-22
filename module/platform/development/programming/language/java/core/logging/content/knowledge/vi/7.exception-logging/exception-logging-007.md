# Không che mất nguyên nhân khi exception logging trong Java

## 1. Mục tiêu: giữ lại chứng cứ dẫn tới lỗi

Khi một thao tác Java thất bại, exception thường chứa nhiều thông tin hơn câu thông báo lỗi hiển thị cho người dùng. **“Không che mất nguyên nhân”** nghĩa là trong quá trình bắt, chuyển đổi, ghi log hoặc phát lại exception, ta cần giữ được bằng chứng cần thiết để truy ngược về sự cố thực sự: **loại lỗi, vị trí phát sinh, nguyên nhân trước đó, ngữ cảnh xử lý và các lỗi phụ nếu có**.

Ví dụ, một thao tác tải đơn hàng thất bại ở tầng ứng dụng, nhưng nguyên nhân ban đầu là timeout ở tầng lưu trữ:

~~~text
IllegalStateException: Cannot load orderId=O-42
    Caused by: IOException: connection timed out
~~~

Nếu tầng ứng dụng chỉ ném `new IllegalStateException("Cannot load order")` mà bỏ đối tượng `IOException`, người điều tra có thể biết thao tác nào không thành công nhưng không còn thấy **vì sao** việc tải đơn hàng thất bại. Ngược lại, nếu tầng ứng dụng ghi thêm ngữ cảnh rồi truyền exception gốc làm cause, log có thể kể lại cả chuỗi lỗi.

Giữ nguyên nhân **không đồng nghĩa với in stack trace ở mọi tầng**. Một exception được bảo toàn có thể được log một lần ở ranh giới chịu trách nhiệm ghi nhận thất bại. Trách nhiệm của tầng trung gian là giữ và bổ sung ngữ cảnh, tránh làm mất dấu vết.

Bài học này giải thích:

- Những gì một `Throwable` chứa và cách đọc chuỗi `Caused by`.
- Các thao tác thường che mất nguyên nhân: nuốt exception, ném exception mới không có cause, chỉ log message, `finally` ném lỗi khác, hoặc xóa trạng thái interrupt.
- Khi nào nên rethrow, khi nào nên wrap và cách ghi log đúng với JUL/SLF4J.
- Cách đọc **suppressed exceptions** từ `try-with-resources`, phân biệt lỗi chính và lỗi phát sinh khi đóng tài nguyên.
- Cách vừa giữ thông tin chẩn đoán trong hệ thống vừa hạn chế rò rỉ thông tin ra bên ngoài.

## 2. Hiểu cấu trúc Throwable trước khi xử lý

Trong Java, `Exception` và `Error` đều kế thừa `Throwable`. Một đối tượng `Throwable` có thể chứa:

| Thành phần | Cách truy cập | Giá trị khi điều tra |
| --- | --- | --- |
| Loại exception | `e.getClass()` | Nhận biết lỗi I/O, lỗi nghiệp vụ, vi phạm trạng thái, v.v. |
| Message | `e.getMessage()` | Mô tả ngắn về lỗi ở tầng tạo exception |
| Stack trace | `e.getStackTrace()`, `e.printStackTrace()` | Đường gọi tới vị trí tạo/ghi nhận exception, tùy cách đối tượng được tạo |
| Cause | `e.getCause()` | Exception nằm bên dưới, giải thích vì sao exception hiện tại phát sinh |
| Suppressed | `e.getSuppressed()` | Những exception phụ được giữ lại khi xử lý exception chính, thường gặp lúc đóng resource |

**Message không thay thế stack trace.** `getMessage()` có thể chỉ cho biết “connection timed out”, trong khi stack trace chỉ tới phương thức gọi kết nối và đường đi tới đó. **Cause** giúp nối một lỗi ở tầng cao với lỗi ở tầng thấp. **Suppressed** lưu lỗi bổ sung không nên thay thế lỗi chính.

Giả sử có chuỗi:

~~~text
IllegalStateException: Cannot finish checkout orderId=O-42
  caused by: RepositoryException: Cannot read inventory
    caused by: SocketTimeoutException: Read timed out
~~~

Exception ngoài cùng mô tả **thao tác thất bại theo ngôn ngữ của tầng hiện tại**. Cause bên trong mô tả **cơ chế kỹ thuật dẫn tới thất bại**. Người điều tra thường bắt đầu từ lỗi ngoài cùng, đọc theo `Caused by` rồi đối chiếu stack trace và bối cảnh thực thi. Không phải exception sâu nhất lúc nào cũng tự động là “nguyên nhân nghiệp vụ cuối cùng”; nó là nguyên nhân được ghi nhận sâu nhất trong **chuỗi hiện có**.

### Exception translation không có nghĩa là mất cause

Việc chuyển một lỗi checked sang unchecked, hoặc chuyển lỗi I/O thành lỗi của domain, là hợp lý khi ranh giới giữa các tầng có hợp đồng khác nhau. Điều cần tránh là chỉ sao chép message:

~~~java
// Sai: IOException gốc không còn được gắn vào exception mới.
catch (IOException e) {
    throw new IllegalStateException("Cannot read configuration");
}
~~~

Cách đúng hơn:

~~~java
// Đúng: giữ exception gốc để stack trace có phần "Caused by".
catch (IOException e) {
    throw new IllegalStateException("Cannot read configuration", e);
}
~~~

Hai đoạn trên là **mã minh họa trong một phương thức có thể bắt IOException**, không phải chương trình độc lập. Constructor `IllegalStateException(String, Throwable)` lưu `e` vào cause; các đối tượng exception vẫn có stack trace riêng. Chuỗi `Caused by` cho phép người xử lý lỗi truy lại tầng phát sinh.

## 3. Bốn mẫu xử lý exception cơ bản

### 3.1. Rethrow: không làm thay đổi ý nghĩa lỗi

Nếu tầng hiện tại không thể xử lý, và hợp đồng của phương thức cho phép phát lại lỗi gốc:

~~~java
// Phương thức minh họa khai báo throws IOException.
try {
    readConfiguration();
} catch (IOException e) {
    // Có thể dọn dẹp không gây lỗi hoặc thêm metric phù hợp ở đây.
    throw e;
}
~~~

`throw e` truyền lại cùng đối tượng exception và cause/stack trace đang có; không nhất thiết phải bao thêm một exception mới. Đừng gọi `e.fillInStackTrace()` chỉ để rethrow: phương thức này cập nhật stack trace của exception và có thể làm khó tìm vị trí ban đầu.

Nếu không thêm xử lý nào, thường **không cần viết catch rồi rethrow**; cứ để exception lan truyền theo khai báo `throws`.

### 3.2. Wrap: thêm ngữ cảnh, bảo toàn cause

Tầng service có thể biết một ID, tên tác vụ hoặc ranh giới nghiệp vụ mà tầng I/O không biết. Khi đó wrap hợp lý:

~~~java
// Minh họa bên trong phương thức service.
try {
    repository.fetch(orderId);
} catch (IOException e) {
    throw new IllegalStateException(
            "Cannot load orderId=" + safeOrderId, e);
}
~~~

Thông điệp ở tầng service trả lời **thao tác nào thất bại**; cause trả lời **cơ chế gây lỗi ở tầng dưới**. `safeOrderId` là ID đã được đánh giá theo chính sách dữ liệu của ứng dụng. Đừng đưa token, thông tin tài khoản hay câu truy vấn chứa dữ liệu nhạy cảm vào message.

Việc wrap không nên vô hạn. Nếu mỗi tầng tạo thêm một wrapper không có thông tin mới, chuỗi cause trở nên dài và khó đọc. Mỗi wrapper cần mang **ngữ cảnh hữu ích hoặc chuyển đổi đúng hợp đồng API**.

### 3.3. Handle: xử lý lỗi đã được dự liệu

Không phải exception nào cũng phải truyền ra ngoài. Ví dụ: một cấu hình tùy chọn không tồn tại và ứng dụng có default đã được tài liệu hóa. Khi đó có thể bắt exception cụ thể, thực hiện fallback và ghi một bản ghi ở mức phù hợp nếu cần.

~~~java
// Minh họa một nhánh fallback đã được phép theo yêu cầu ứng dụng.
try {
    return loadOptionalConfig();
} catch (NoSuchFileException e) {
    LOG.log(Level.INFO, "Optional config missing; using defaults", e);
    return defaultConfig();
}
~~~

Đoạn này minh họa trong một phương thức có `LOG`, `loadOptionalConfig` và `defaultConfig` tương ứng. Cần phân biệt **không tìm thấy file tùy chọn** (có thể dự kiến) với các lỗi như quyền truy cập hoặc lỗi đọc nội dung (không mặc định được phép fallback). Catch đúng loại giúp tránh vô tình che một sự cố hạ tầng bằng giá trị default.

Có trường hợp fallback là hoạt động bình thường nên chỉ cần metric hoặc log ngắn, không nhất thiết in stack trace ở mức ERROR. Quyết định phải dựa vào yêu cầu vận hành, không phải nguyên tắc “log mọi exception”.

### 3.4. Log ở ranh giới chịu trách nhiệm, không log trùng khắp nơi

Một đường đi thường hợp lý:

~~~text
Repository   : throw IOException
Service      : wrap IllegalStateException(..., cause)
API boundary : log Throwable với requestId, trả response an toàn
~~~

Nếu repository, service và controller đều ghi cùng lỗi ở mức ERROR rồi tiếp tục ném lên, một failure duy nhất có thể xuất hiện thành ba log lỗi. Điều đó gây nhiễu và làm sai thống kê. Hãy chọn một nơi **chịu trách nhiệm ghi log kết quả thất bại**, trong khi các tầng trung gian chỉ cần bổ sung ngữ cảnh khi thực sự có thông tin mới.

**Không che nguyên nhân** và **không log trùng** là hai mục tiêu cùng thực hiện được: giữ cause xuyên suốt, log đầy đủ ở đúng ranh giới.

## 4. Những kiểu mã làm nguyên nhân biến mất

### Sai lầm 1: catch rồi bỏ qua

~~~java
try {
    updateRemoteState();
} catch (Exception ignored) {
    // Không có phản ứng, không giữ nguyên nhân.
}
~~~

Việc này có thể tạo cảm giác thao tác thành công dù sự cố đã xảy ra. Nếu thật sự được phép bỏ qua một exception cụ thể, phải có lý do rõ ràng và hành vi tiếp theo có thể kiểm chứng. Catch `Exception` rộng để bỏ qua tất cả lỗi thường che cả những tình huống chưa từng dự liệu.

### Sai lầm 2: chỉ giữ getMessage()

~~~java
catch (IOException e) {
    throw new RuntimeException(e.getMessage());
}
~~~

Exception mới chứa nội dung text của `IOException` nhưng **không chứa đối tượng lỗi gốc**. Thông tin loại và stack trace gốc không còn được liên kết bằng `getCause()`. Hãy dùng:

~~~java
catch (IOException e) {
    throw new RuntimeException("Read operation failed", e);
}
~~~

### Sai lầm 3: log chuỗi thay vì Throwable

~~~java
catch (IOException e) {
    LOG.severe("Failed: " + e.getMessage());
    throw e;
}
~~~

Dòng log này không đính kèm đối tượng `Throwable`; nếu chỉ nhìn vào bản ghi đó, ta không có stack trace. Rethrow vẫn giữ exception trong luồng thực thi, nhưng bản ghi logger chưa đủ để điều tra nếu không có nơi nào log Throwable sau đó.

Với JUL, khi đây là nơi cần báo cáo lỗi, dùng overload có Throwable:

~~~java
catch (IOException e) {
    LOG.log(Level.SEVERE, "operation=readConfig outcome=failed", e);
    throw e;
}
~~~

`Logger.log(Level, String, Throwable)` đưa `Throwable` vào `LogRecord`. Formatter/handler thích hợp sẽ hiển thị stack trace và cause. Nếu đã có ranh giới khác chịu trách nhiệm log exception, cân nhắc để nơi đó ghi một lần.

### Sai lầm 4: ném exception mới từ finally

~~~java
// Ví dụ minh họa: exception ở finally có thể che exception trước đó.
try {
    throw new IOException("read failed");
} finally {
    throw new IllegalStateException("cleanup failed");
}
~~~

Exception thoát ra ngoài là `IllegalStateException("cleanup failed")`; exception từ khối `try` đã bị thay thế. Tránh đặt các thao tác cleanup có thể ném lỗi không kiểm soát trong `finally`. Dùng `try-with-resources` cho resource phù hợp để Java lưu lỗi close dưới dạng suppressed khi có lỗi chính.

Không nên đặt `return` trong `finally`: nó cũng có thể làm lỗi đang được ném biến mất khỏi luồng điều khiển.

### Sai lầm 5: bắt rộng rồi trả giá trị “hợp lệ” giả

~~~java
// Không nên: người gọi có thể hiểu 0 là kết quả thật.
try {
    return calculateTotal();
} catch (Exception e) {
    return 0;
}
~~~

Nếu `0` là một giá trị nghiệp vụ hợp lệ, lỗi bị biến thành dữ liệu và có thể lan sang những thao tác sau. Chỉ fallback khi đó là yêu cầu rõ ràng của nghiệp vụ, có loại exception cụ thể và kết quả phân biệt được trạng thái fallback nếu cần.

### Sai lầm 6: tạo lại exception theo message của exception khác

Đôi khi người viết mã chọn `new IOException(e.toString())`, `new IllegalArgumentException(e.getMessage())` hoặc chỉ copy code lỗi. Những thao tác này có thể giữ vài chữ nhưng làm mất **cause** và mối liên kết với stack trace gốc. Chọn constructor nhận `Throwable` hoặc thiết kế exception domain hỗ trợ cause.

## 5. Ví dụ Java 17 chạy độc lập: cause, log và suppressed exception

Ví dụ sau mô phỏng lỗi I/O tại tầng lưu trữ; tầng service chuyển thành `IllegalStateException` kèm ID nghiệp vụ và giữ `IOException` làm cause. Logger JUL nhận Throwable. Một handler nhỏ chỉ in thông tin có thể kiểm chứng để stdout ổn định; nó **không thay thế formatter production** (nơi thường hiển thị đầy đủ stack trace).

Tạo tệp **PreserveCauseDemo.java**:

~~~java
import java.io.IOException;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class PreserveCauseDemo {
    private static final Logger LOG =
            Logger.getLogger(PreserveCauseDemo.class.getName());

    static String readFromStore(String recordId) throws IOException {
        throw new IOException("connection timed out");
    }

    static String loadRecord(String recordId) {
        try {
            return readFromStore(recordId);
        } catch (IOException e) {
            throw new IllegalStateException(
                    "Cannot load recordId=" + recordId, e);
        }
    }

    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void showSuppressed() {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("read failed");
        } catch (IOException e) {
            System.out.println("primary=" + e.getMessage());
            System.out.println("suppressedCount=" + e.getSuppressed().length);
            System.out.println("suppressed[0]="
                    + e.getSuppressed()[0].getMessage());
        }
    }

    static void configureDemoLogger() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }
                System.out.println(record.getLevel().getName()
                        + " " + record.getMessage());

                Throwable thrown = record.getThrown();
                if (thrown != null) {
                    System.out.println("loggedThrowable="
                            + thrown.getClass().getSimpleName());
                    if (thrown.getCause() != null) {
                        System.out.println("loggedCause="
                                + thrown.getCause()
                                        .getClass().getSimpleName());
                    }
                }
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };

        handler.setLevel(Level.ALL);
        LOG.addHandler(handler);
    }

    public static void main(String[] args) {
        configureDemoLogger();

        try {
            loadRecord("R-42");
        } catch (IllegalStateException e) {
            LOG.log(Level.SEVERE,
                    "operation=loadRecord recordId=R-42 outcome=failed", e);

            System.out.println("outer=" + e.getClass().getSimpleName()
                    + ": " + e.getMessage());
            System.out.println("cause="
                    + e.getCause().getClass().getSimpleName()
                    + ": " + e.getCause().getMessage());
        }

        showSuppressed();
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 PreserveCauseDemo.java
java PreserveCauseDemo
~~~

**Stdout chính xác** của chương trình:

~~~text
SEVERE operation=loadRecord recordId=R-42 outcome=failed
loggedThrowable=IllegalStateException
loggedCause=IOException
outer=IllegalStateException: Cannot load recordId=R-42
cause=IOException: connection timed out
primary=read failed
suppressedCount=1
suppressed[0]=close failed
~~~

Phân tích:

1. `readFromStore` ném `IOException("connection timed out")`.
2. `loadRecord` bắt và tạo `IllegalStateException("Cannot load recordId=R-42", e)`. Do có tham số `e`, phương thức `getCause()` ở exception mới vẫn trả về `IOException` ban đầu.
3. Tại ranh giới trong `main`, `LOG.log(Level.SEVERE, message, e)` chuyển **đúng đối tượng exception** tới logger. Handler minh họa cho thấy `record.getThrown()` là `IllegalStateException` và cause là `IOException`. Handler cố ý chỉ in tên lớp, nên ví dụ không in toàn bộ stack trace; formatter JUL thông thường có thể in stack trace và chuỗi `Caused by`.
4. Trong `showSuppressed`, khối `try` ném `IOException("read failed")` và `close()` cũng ném `IOException("close failed")`. Java giữ exception đọc làm **primary**, gắn exception khi đóng vào mảng `getSuppressed()`. Vì vậy số suppressed bằng 1, không che mất lỗi đọc.

Các giá trị `getCause()` và `getSuppressed()` được kiểm tra trong một tình huống mà chương trình đã biết rõ cấu trúc exception. Trong mã tổng quát, **không** truy cập `getCause().getMessage()` hoặc `getSuppressed()[0]` nếu chưa kiểm tra cause khác `null` và mảng suppressed có phần tử.

## 6. Ghi đúng exception trong JUL và SLF4J

### 6.1. java.util.logging (JUL)

Trong JUL, dùng một overload dành cho Throwable:

~~~java
// Minh họa trong catch có LOG, recordId và IOException e.
LOG.log(Level.SEVERE, "operation=loadRecord outcome=failed", e);
~~~

`LogRecord.getThrown()` sẽ chứa exception được truyền vào. Với `SimpleFormatter` hoặc formatter hỗ trợ Throwable, log hiển thị stack trace cùng cause; người đọc có thể xem phần `Caused by` để tìm exception bên dưới.

Cẩn thận với overload **không nhận Throwable**:

~~~java
LOG.severe("Load failed: " + e.getMessage());
~~~

Dòng này chỉ tạo một message text. Nếu log này là bằng chứng duy nhất còn lại, nguyên nhân mất đi ở tầng quan sát, dù đối tượng `e` có thể vẫn tồn tại bên trong thread.

### 6.2. SLF4J

Trong một dự án đã có SLF4J và provider/backend:

~~~java
// Minh họa trong catch; LOG là org.slf4j.Logger.
LOG.error("operation=loadRecord recordId={} outcome=failed",
        recordId, e);
~~~

Trong cách dùng parameterized logging thông thường của SLF4J, **Throwable cuối cùng** được nhận diện là exception của sự kiện và được chuyển tới backend để in stack trace. Không cần tạo placeholder `{}` riêng dành cho Throwable. Với chỉ exception, cũng có overload `error(String, Throwable)`:

~~~java
LOG.error("Load record failed", e);
~~~

Đừng thay bằng:

~~~java
LOG.error("Load record failed: {}", e.getMessage());
~~~

Cách sau chỉ truyền chuỗi message của exception. Nó không đính kèm Throwable, không bảo toàn stack trace trên bản ghi đó.

**Đầu ra thật phụ thuộc logger và backend.** Mức logger, appender/filter, formatter/encoder có thể làm một event bị chặn hoặc chỉ hiện một phần. Khi điều tra, kiểm tra cả cấu hình chấp nhận event và việc encoder có đưa throwable/cause/suppressed vào log hay không.

### 6.3. Log một lần và truyền nguyên nhân xuyên tầng

Nếu tầng repository throw, tầng service wrap, tầng HTTP đã log Throwable đầy đủ và chuyển lỗi thành response an toàn, service thường không cần ghi thêm `ERROR` cho cùng exception. Tối ưu này không làm mất nguyên nhân, vì `throw new DomainException(message, e)` giữ cause đến ranh giới log.

Nếu một exception được **xử lý hoàn toàn tại chỗ** (ví dụ retry thành công hoặc fallback hợp lệ), nơi xử lý có thể ghi log mức thích hợp hoặc metric. Không có quy tắc cứng rằng chỉ được log một lần trong mọi hệ thống; mục tiêu là **tránh các bản ghi trùng không mang thêm thông tin**.

## 7. Cause chain và suppressed exceptions khác nhau thế nào?

Giả sử một request có thể trải qua:

~~~text
ServiceException
  Caused by: RepositoryException
    Caused by: SQLException
~~~

`getCause()` mô tả các lớp lỗi **đã được bọc và truyền lên**. Khi muốn tìm nguyên nhân sâu hơn, có thể đi từng bước qua `e.getCause()` cho tới `null`. Nhưng hãy giữ cả exception ngoài cùng khi báo cáo, vì nó cho biết thao tác nào đã thất bại.

Ví dụ một hàm **minh họa** để duyệt cause mà không làm rơi thông tin:

~~~java
static void printCauseChain(Throwable failure) {
    int depth = 0;
    for (Throwable current = failure;
         current != null;
         current = current.getCause()) {
        System.out.println("depth=" + depth
                + " type=" + current.getClass().getName()
                + " message=" + current.getMessage());
        depth++;
    }
}
~~~

Đoạn minh họa trên giả định chuỗi cause không có vòng; Java thường ngăn gắn exception làm cause của chính nó, nhưng những cấu trúc Throwable bất thường do mã tùy biến hoặc reflection có thể cần kiểm soát vòng lặp. Để hiển thị chẩn đoán hoàn chỉnh, dùng formatter chuẩn hoặc công cụ quản lý lỗi thay vì tự dựng lại stack trace với một chuỗi message.

**Suppressed exceptions** là một nhánh khác, **không phải** một mắt xích của `getCause()`. Chúng thường xuất hiện khi lỗi trong khối `try` và lỗi khi đóng resource cùng xảy ra. Ví dụ:

~~~java
try (InputStream input = openStream()) {
    parse(input);               // Có thể ném lỗi chính.
}                               // close() cũng có thể thất bại.
~~~

Nếu `parse(input)` ném một exception, còn `close()` ném exception khác, `try-with-resources` giữ lỗi parse là primary và gắn lỗi close vào `primary.getSuppressed()`. Nếu phần thân không ném lỗi mà chỉ `close()` thất bại, exception close có thể trở thành lỗi chính. Do đó **không nên khẳng định exception trong suppressed luôn xuất hiện, hay luôn là nguyên nhân gốc**.

Khi chẩn đoán, xem cả:

- Chuỗi `getCause()`: vì sao lỗi cấp cao được tạo.
- Danh sách `getSuppressed()` trên từng Throwable nếu cần: lỗi nào xảy ra thêm trong quá trình xử lý/đóng resource.
- Stack trace và thông điệp ở từng tầng: thao tác, vị trí và điều kiện cụ thể.

## 8. Try-with-resources giúp giữ lỗi chính

Trước Java 7, cleanup trong `finally` dễ vô tình ném exception mới và che exception từ công việc chính. Với đối tượng triển khai `AutoCloseable`, `try-with-resources` cung cấp cơ chế đóng tài nguyên và suppressed exceptions:

~~~java
// Minh họa: resource implements AutoCloseable.
try (MyResource resource = acquire()) {
    resource.process();
}
~~~

Nếu `process()` lỗi và `close()` lỗi, Java sử dụng quy tắc primary/suppressed như mục 7. Điều này giúp không làm mất lỗi nghiệp vụ chỉ vì tài nguyên đóng không thành công.

Tuy nhiên, vẫn cần xem log formatter có in suppressed hay không. Nếu một hệ thống chỉ ghi `getMessage()` của exception ngoài cùng, lỗi đóng resource có thể tồn tại trong đối tượng nhưng **không hiện trên log**.

Tránh biến lỗi close thành lỗi chính theo kiểu:

~~~java
// Có thể làm lỗi từ businessOperation() bị che.
try {
    businessOperation();
} finally {
    closeThatMayThrow();
}
~~~

Có thể sử dụng `try-with-resources` hoặc thiết kế cleanup biết cách bảo toàn exception chính; không nên tự động catch rồi bỏ mọi lỗi close, vì lỗi đó cũng có thể quan trọng.

## 9. Không che tín hiệu ngắt thread và lỗi bất đồng bộ

### 9.1. InterruptedException

`InterruptedException` là tín hiệu cơ chế hủy/chờ ngắt, không phải lỗi thông thường có thể luôn bỏ qua. Nhiều phương thức blocking của Java sẽ **xóa cờ interrupt khi ném InterruptedException**. Khi mã không thể truyền trực tiếp `InterruptedException` theo hợp đồng, thường cần khôi phục cờ và bọc cause:

~~~java
// Minh họa trong phương thức không khai báo throws InterruptedException.
try {
    Thread.sleep(1_000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // Khôi phục tín hiệu ngắt.
    throw new IllegalStateException("Worker interrupted while waiting", e);
}
~~~

Với phương thức có thể khai báo `throws InterruptedException`, có thể truyền trực tiếp `throw e` và để tầng gọi quyết định hủy/gián đoạn. Không catch rồi im lặng tiếp tục vòng lặp vô hạn: khi đó nguyên nhân yêu cầu dừng và cả trạng thái interrupt có thể bị đánh mất.

### 9.2. CompletionException và ExecutionException

Tác vụ bất đồng bộ như `CompletableFuture.join()` có thể ném `CompletionException`; `Future.get()` có thể ném `ExecutionException`. Chúng thường giữ lỗi từ tác vụ gốc trong `getCause()`. Nếu chỉ log:

~~~java
// Không nên chỉ ghi thông điệp của wrapper.
LOG.warning("Async task failed: " + e.getMessage());
~~~

thì có thể bỏ qua exception ở tác vụ thực thi. Hãy log Throwable hoặc kiểm tra cause khi cần phân loại lỗi:

~~~java
// Minh họa trong catch (ExecutionException e) với JUL Logger LOG.
LOG.log(Level.SEVERE, "Background operation failed", e);
~~~

Thông thường không cần “bóc” mọi wrapper bằng cách ném lại cause nguyên gốc nếu hợp đồng tầng hiện tại không cho phép: wrapper cung cấp thông tin về ranh giới async. Có thể tạo exception domain mới mang ngữ cảnh và giữ wrapper hoặc cause phù hợp theo API.

Tránh xử lý `CancellationException` như một lỗi hệ thống nghiêm trọng trong mọi tình huống: một tác vụ bị hủy có thể là hành vi dự kiến. Điều cốt lõi là phân biệt hủy, ngắt và thất bại thật, đồng thời giữ nguyên thông tin cần thiết cho tầng xử lý.

## 10. Bảo toàn nguyên nhân không đồng nghĩa với lộ dữ liệu

Stack trace, message của driver/database và thông tin về đường dẫn tài nguyên đôi khi chứa dữ liệu nhạy cảm: endpoint nội bộ, đường dẫn hệ thống, query có tham số, username hoặc chi tiết vận hành. **Giữ cause bên trong hệ thống** vẫn có thể đi cùng **response bên ngoài được giới hạn thông tin**.

Một mô hình phù hợp:

~~~text
Internal logger:
  operation=loadOrder requestId=req-8 outcome=failed
  Throwable: IllegalStateException ... Caused by: SQLException ...

Public API response:
  status=500
  errorCode=ORDER_LOAD_FAILED
  message=Cannot complete the request
  requestId=req-8
~~~

Các dòng trên là **minh họa cấu trúc**, không phải chuẩn HTTP bắt buộc. Người dùng cuối nhận một thông điệp an toàn và ID để hỗ trợ; hệ thống ghi log nội bộ giữ cause/stack trace ở nơi có quyền truy cập phù hợp.

Thực hành an toàn gồm:

- Đặt thông điệp exception **rõ về thao tác**, không đưa password/token/cookie hoặc toàn bộ request payload.
- Chọn `requestId`, mã lỗi, tên thao tác và định danh đã được kiểm soát thay vì dữ liệu cá nhân không cần thiết.
- Dùng encoder/formatter bảo vệ trước newline/ký tự điều khiển từ input không tin cậy (tránh log forging).
- Chỉ ghi Throwable đầy đủ tại nơi cần và được phép xem; giới hạn retention, quyền truy cập và việc gửi ra hệ thống thứ ba.
- Đừng xóa cause một cách vô điều kiện để “an toàn”; thay vào đó kiểm soát **đích log và dữ liệu phơi bày** theo mục đích.

## 11. Khi nào cần wrap, khi nào cần rethrow?

| Tình huống | Hướng xử lý gợi ý | Vì sao |
| --- | --- | --- |
| Phương thức chỉ truyền lỗi cùng hợp đồng | Rethrow hoặc không catch | Giữ đúng loại và stack trace, tránh mã dư |
| Chuyển từ tầng lưu trữ sang tầng nghiệp vụ | Wrap bằng exception có constructor nhận cause | Bổ sung ngữ cảnh hữu ích mà vẫn bảo toàn lỗi gốc |
| Lỗi cấu hình tùy chọn đã có fallback được phép | Catch loại cụ thể, dùng fallback, ghi/đo theo yêu cầu | Đây là nhánh xử lý có dự kiến, cần phân biệt với lỗi hạ tầng |
| Ranh giới HTTP hoặc job runner | Log Throwable với ID tương quan, chuyển thành kết quả an toàn | Tập trung trách nhiệm báo lỗi, tránh log nhiều lần |
| Try-with-resources có lỗi close | Xem primary và suppressed | Không nhầm lỗi đóng tài nguyên với lỗi của tác vụ |
| Tác vụ bị interrupt | Rethrow hoặc restore interrupt rồi propagate phù hợp | Không nuốt tín hiệu điều phối thread |
| Future/async thất bại | Kiểm tra exception bao ngoài và cause | Giữ bối cảnh bất đồng bộ và lỗi của tác vụ |
| Lỗi bị bắt trong một bộ phận có thể retry | Chỉ retry loại lỗi được phép; giữ lỗi cuối và lịch sử cần thiết | Không che nguyên nhân bằng thông báo “retry failed” chung chung |

Để tạo class exception riêng, nên cung cấp constructor có cause:

~~~java
// Ví dụ độc lập về định nghĩa class exception tùy biến.
public class OrderLoadException extends RuntimeException {
    public OrderLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Tại nơi catch:

~~~java
throw new OrderLoadException(
        "Cannot load orderId=" + safeOrderId, e);
~~~

Đoạn ném lỗi thứ hai cần có `safeOrderId` và `e` trong phạm vi. Constructor gọi `super(message, cause)` là điểm quan trọng để không mất cause. Tránh tạo exception domain chỉ nhận `String message` nếu nó thường được dùng để bao một exception tầng dưới.

## 12. Quy trình điều tra khi log dường như thiếu nguyên nhân

1. **Xác định bản ghi của một failure:** dùng `requestId`, `operation`, thời điểm và phiên bản ứng dụng để gom đúng sự kiện, thay vì chỉ tìm từ khóa “error” trên mọi thread.
2. **Tìm stack trace thực sự:** bản ghi có Throwable/`Caused by` hay chỉ `e.getMessage()`? Nếu chỉ có chuỗi, tìm ranh giới khác có ghi đầy đủ.
3. **Đọc exception ngoài cùng và cause chain:** ghi lại loại lỗi, message và vị trí stack trace ở từng tầng. Xác định xem tầng service có wrap mà quên truyền cause không.
4. **Kiểm tra suppressed exceptions:** nếu lỗi liên quan resource hoặc cleanup, xem `Suppressed: ...` và `getSuppressed()`. Phân biệt lỗi trong tác vụ với lỗi đóng tài nguyên.
5. **Kiểm tra nơi lỗi bị biến thành kết quả giả:** catch rỗng, catch `Exception` rộng, fallback `null`/`0`/empty list, hoặc handler trả về success dù thao tác thực đã thất bại.
6. **Kiểm tra async/interrupt:** có `ExecutionException`, `CompletionException` hoặc `InterruptedException` bị lọc/bỏ qua không?
7. **Sửa đúng ranh giới rồi tạo regression test:** xác minh vừa có hành vi nghiệp vụ đúng, vừa giữ được `getCause()`, suppressed khi có và bản ghi log đủ ngữ cảnh, không lộ bí mật.

Khi test chuỗi cause, không nhất thiết so khớp nguyên văn mọi stack trace vì số dòng có thể thay đổi theo refactor. Thay vào đó có thể assert **loại cause, message hoặc mã lỗi phù hợp, và quan hệ giữa wrapper với cause**. Với thử nghiệm try-with-resources, assert mảng suppressed chứa exception close mong đợi.

## 13. Các lỗi phổ biến và cách tránh

| Lỗi | Điều bị mất hoặc bị sai | Cách sửa |
| --- | --- | --- |
| `catch (Exception ignored) {}` | Không còn dấu vết và hành vi xử lý có thể giả thành công | Catch loại cụ thể và xử lý có chủ đích |
| `new RuntimeException(e.getMessage())` | Mất liên kết với đối tượng cause | `new RuntimeException("context", e)` |
| `LOG.severe(e.getMessage())` làm log lỗi duy nhất | Log không có Throwable/stack trace | Dùng `LOG.log(Level.SEVERE, message, e)` |
| `throw new X("failed")` ở mọi tầng | Không biết lỗi khởi nguồn | Wrap khi cần, giữ cause và bối cảnh |
| Log ERROR rồi rethrow ở mọi lớp | Log trùng, cảnh báo đếm sai | Chọn ranh giới log phù hợp |
| `finally` ném exception hoặc return | Che lỗi từ khối `try` | Dùng try-with-resources/cleanup bảo toàn primary |
| Chỉ xem `getCause()` | Bỏ sót lỗi suppressed khi đóng resource | Xem cả `getSuppressed()` |
| Coi exception ngoài cùng là nguyên nhân sâu nhất | Bỏ qua `Caused by` và stack trace bên dưới | Theo cause chain và đọc toàn bộ ngữ cảnh |
| Catch `InterruptedException` rồi tiếp tục | Có thể xóa tín hiệu interrupt | Propagate hoặc restore interrupt |
| Trả nguyên stack trace ra HTTP response | Lộ chi tiết nội bộ không cần thiết | Log nội bộ có quyền kiểm soát, response an toàn |
| Dùng Throwable trong message text đã format | Stack trace có thể bị mất trong log | Truyền đối tượng Throwable theo đúng API |

## 14. Bài tập tự kiểm tra

1. **Dự đoán cause:** với `throw new IllegalStateException("Cannot load", new IOException("timeout"))`, hãy nêu loại, message của exception ngoài cùng và cause. So sánh với `new IllegalStateException("Cannot load")`.
2. **Chạy ví dụ:** biên dịch `PreserveCauseDemo.java` bằng JDK 17, giải thích tại sao `loggedCause=IOException`, `cause=IOException: connection timed out` và `suppressedCount=1`. Nếu thay constructor thành `new IllegalStateException("Cannot load recordId=" + recordId)`, truy cập `e.getCause().getClass()` sẽ dẫn tới tình huống nào?
3. **Sửa đoạn mã:** thay `catch (IOException e) { LOG.severe(e.getMessage()); throw new RuntimeException("failed"); }` bằng cách giữ cause và chỉ log tại nơi được phân công báo cáo lỗi.
4. **Try-with-resources:** làm cho khối xử lý thành công còn `close()` ném lỗi, so sánh exception thoát ra với trường hợp cả `process()` và `close()` cùng ném lỗi.
5. **Bất đồng bộ:** với một `CompletableFuture` hoàn tất bất thường bằng `IOException`, phân tích exception khi gọi `join()` và cách đọc `getCause()`; không coi text message của wrapper là toàn bộ thông tin.
6. **Thiết kế API:** đề xuất một log nội bộ bảo toàn Throwable và một response JSON an toàn cho lỗi tải đơn hàng; giải thích vì sao hai bên có mức thông tin khác nhau.
7. **Regression test:** mô tả hai assertion quan trọng nhất cho một exception domain được tạo bằng cách wrap `SQLException`, và cách kiểm tra log có chứa Throwable thay vì chỉ chứa message.

**Ghi nhớ:** khi một lỗi đi qua nhiều tầng, hãy giữ exception gốc làm **cause**, bảo toàn lỗi phụ dạng **suppressed**, ghi **Throwable** đúng overload, và thêm ngữ cảnh đúng chỗ. Đừng để catch rỗng, wrapper không có cause, `finally` hoặc log chỉ chứa message khiến người điều tra không còn tìm được nguyên nhân thực sự.