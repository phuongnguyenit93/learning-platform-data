# Cause chain trong Exception Logging của Java

## 1. Cause chain là gì?

Trong Java, **cause chain** (chuỗi nguyên nhân ngoại lệ) là quan hệ nối từ một ngoại lệ ở tầng xử lý hiện tại đến ngoại lệ đã gây ra nó, rồi tiếp tục đến nguyên nhân sâu hơn nếu có. Java cung cấp cơ chế này qua **Throwable.getCause()** và các constructor nhận đối số **Throwable cause**.

Khi một tầng ứng dụng bắt ngoại lệ từ tầng thấp và cần diễn đạt lỗi theo ngữ cảnh cao hơn, nó có thể **bọc ngoại lệ gốc** vào ngoại lệ mới:

~~~text
OrderProcessingException: Không thể xử lý đơn hàng
    caused by QuantityFormatException: Số lượng không hợp lệ
        caused by NumberFormatException: Không phân tích được số nguyên
~~~

Ba ngoại lệ này tạo thành **một chuỗi nguyên nhân**, không phải ba sự cố độc lập. Ngoại lệ ngoài cùng giải thích tác động nghiệp vụ; ngoại lệ bên trong cho biết thành phần và thao tác gây lỗi; ngoại lệ cuối chuỗi thường gần nguyên nhân kỹ thuật nhất.

Cause chain đặc biệt hữu ích khi đọc log lỗi: nếu chỉ thấy “Không thể xử lý đơn hàng”, bạn chưa biết thất bại do dữ liệu đầu vào, dịch vụ kho hay cơ sở dữ liệu. Nếu log giữ và hiển thị chuỗi nguyên nhân, người vận hành có thể đi từ **triệu chứng ở tầng cao** đến **nguyên nhân ở tầng thấp**.

**Mục tiêu của bài:** hiểu cách tạo, duy trì, đọc và ghi log cause chain đúng cách với Java 17+, đồng thời tránh mất thông tin, log trùng lặp và rò rỉ dữ liệu nhạy cảm.

## 2. Cause chain nằm ở đâu trong cấu trúc Throwable?

Trong Java, **Throwable** là lớp cơ sở của hai nhánh thường gặp:

- **Exception**: mô tả các điều kiện ngoại lệ mà ứng dụng có thể cần xử lý; gồm checked exception và **RuntimeException**.
- **Error**: thường biểu thị vấn đề nghiêm trọng của môi trường/JVM; ứng dụng thông thường không cố xử lý mọi Error bằng cách phục hồi.

Mỗi đối tượng Throwable có thể giữ các thông tin:

| Thông tin | API | Ý nghĩa |
| --- | --- | --- |
| Thông điệp | getMessage() | Mô tả lỗi của ngoại lệ hiện tại |
| Chuỗi nguyên nhân | getCause() | Ngoại lệ gây ra ngoại lệ hiện tại; có thể null |
| Tên loại ngoại lệ | getClass().getName() | Kiểu ngoại lệ cụ thể để điều tra |
| Stack trace | getStackTrace(), printStackTrace() | Những vị trí trong mã liên quan đến nơi ngoại lệ được tạo hoặc được cập nhật stack |
| Suppressed exceptions | getSuppressed() | Những lỗi bị nén, thường phát sinh khi đóng tài nguyên |
| Mô tả tổng quát | toString() | Thường là tên lớp cộng thông điệp nếu có |

**Cause chain** là các liên kết đơn **Throwable → cause → cause tiếp theo**. Khi **getCause() == null**, chuỗi kết thúc. Một ngoại lệ không nhất thiết phải có cause; chẳng hạn ngoại lệ được phát sinh trực tiếp khi kiểm tra dữ liệu mà không bắt ngoại lệ nào trước đó.

**Không nhầm cause với stack trace:**

- Cause cho biết **lỗi nào gây ra lỗi nào**.
- Stack trace cho biết **đường gọi phương thức/điểm tạo của từng Throwable**.
- Một stack trace có thể rất dài nhưng không có cause.
- Một cause chain có thể có nhiều Throwable, và **mỗi Throwable có stack trace riêng**.

Khi dùng **printStackTrace()**, Java có thể hiển thị cả stack trace của ngoại lệ ngoài cùng và các khối **Caused by:** cho những cause bên trong; số dòng và chi tiết phụ thuộc đường thực thi.

## 3. Vì sao cần bọc ngoại lệ thay vì chỉ truyền thông điệp?

Giả sử lớp lưu dữ liệu không thể phân tích một giá trị số. Lớp nghiệp vụ muốn báo thất bại bằng ngôn ngữ phù hợp với đơn hàng.

**Cách sai: mất nguyên nhân gốc**

~~~java
try {
    saveOrderData();
} catch (NumberFormatException e) {
    throw new OrderProcessingException("Cannot save order");
}
~~~

Đoạn trên giả định các phương thức/lớp đã tồn tại và là **snippet**, không phải chương trình độc lập. Do constructor mới không nhận **e**, **getCause()** của ngoại lệ được ném ra có thể là null, và khi đọc log người điều tra không còn liên kết trực tiếp tới NumberFormatException ban đầu.

**Cách đúng: giữ Throwable gốc làm cause**

~~~java
try {
    saveOrderData();
} catch (NumberFormatException e) {
    throw new OrderProcessingException("Cannot save order", e);
}
~~~

Trong lớp OrderProcessingException cần constructor chuyển cause cho lớp cha:

~~~java
public class OrderProcessingException extends RuntimeException {
    public OrderProcessingException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Ví dụ ở trên minh họa **cách khai báo lớp ngoại lệ**, có thể lưu thành OrderProcessingException.java nếu muốn dùng độc lập cùng mã gọi phù hợp. Constructor **super(message, cause)** vừa giữ thông điệp ở tầng nghiệp vụ vừa giữ ngoại lệ đã bắt.

Với checked exception, có thể dùng cơ chế tương tự:

~~~java
public class OrderStorageException extends Exception {
    public OrderStorageException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Khi phương thức ném checked exception, nó cần khai báo **throws** hoặc xử lý theo quy tắc Java. Việc bọc lỗi không tự chuyển checked thành unchecked; loại lớp ngoại lệ mới quyết định hợp đồng compile-time.

**Lưu ý:** có những trường hợp chỉ cần **throw e;** để giữ nguyên ngoại lệ và stack trace, nếu tầng hiện tại không cần chuyển đổi loại lỗi. Không bắt rồi bọc ngoại lệ ở mọi phương thức chỉ để tạo nhiều tầng không có thông tin mới.

## 4. Cơ chế tạo và nối cause chain

Có ba cách thường gặp:

### A. Constructor nhận cause

~~~java
throw new IllegalStateException("Order processing failed", original);
~~~

Phương thức khởi tạo này là lựa chọn phổ biến khi bạn muốn **thay đổi ngữ cảnh lỗi** nhưng vẫn bảo toàn Throwable gốc.

### B. Constructor nhận message và cause của lớp tùy chỉnh

~~~java
final class ServiceException extends RuntimeException {
    ServiceException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là mẫu dùng khi tầng nghiệp vụ muốn có loại exception ổn định để phân biệt với ngoại lệ thư viện.

### C. initCause() cho kiểu ngoại lệ cũ

~~~java
Exception legacy = new Exception("Legacy operation failed");
legacy.initCause(original);
throw legacy;
~~~

**initCause(Throwable)** chỉ dùng khi cause **chưa được khởi tạo**. Gọi lại trên cùng một Throwable sau khi cause đã được đặt có thể ném **IllegalStateException**. Java cũng không chấp nhận một Throwable làm cause của chính nó qua **initCause()**. Với những constructor chuẩn đã khởi tạo cause, bao gồm constructor nhận cause kể cả null, đừng gọi initCause lại.

Trong mã hiện đại, nên ưu tiên **constructor(message, cause)** khi có sẵn. **initCause()** chủ yếu phục vụ các lớp ngoại lệ đời cũ không có constructor thích hợp.

### Từng tầng nên thêm gì?

Một chuỗi dễ đọc thường tương ứng với **các ranh giới trách nhiệm thực sự**:

~~~text
Controller / API
  OrderProcessingException: order validation failed
      |
      +-- Domain / validation layer
            QuantityFormatException: quantity must be an integer
                |
                +-- Java parser
                      NumberFormatException: invalid decimal input
~~~

Không bắt buộc tầng Controller phải bọc thêm một exception nữa nếu đã có loại OrderProcessingException phù hợp và chỉ cần chuyển đổi thành HTTP response. Nếu mỗi tầng tạo wrapper mang cùng thông điệp “operation failed”, cause chain dài hơn nhưng không mang thêm giá trị.

## 5. Đọc cause chain bằng getCause()

Cách duyệt đơn giản nhất là bắt đầu từ Throwable ngoài cùng rồi lần lượt gọi **getCause()**:

~~~java
Throwable current = error;
while (current != null) {
    System.out.println(current.getClass().getSimpleName());
    current = current.getCause();
}
~~~

Đây là **snippet** giả định có sẵn biến **error**. Nó phù hợp để giải thích cơ chế, nhưng code production nên phòng vệ trước chuỗi bất thường.

### “Root cause” nghĩa là gì?

Thông thường, **root cause** được hiểu là Throwable cuối cùng có thể tìm thấy qua **getCause()**; đó là vị trí sâu nhất trong chuỗi nguyên nhân, ví dụ NumberFormatException. Tuy nhiên, ngoại lệ sâu nhất **không phải lúc nào cũng là nguyên nhân nghiệp vụ cần sửa**. Một lỗi timeout ở thư viện HTTP có thể là triệu chứng của dịch vụ phụ thuộc đang quá tải; muốn tìm lý do gốc theo nghĩa vận hành còn cần log khác, metric và tracing.

Java SE không cung cấp một quy tắc nghiệp vụ chung để chọn ngoại lệ quan trọng nhất. Tên helper **getRootCause()** của một số thư viện không đồng nghĩa đó là phương thức có sẵn trên **java.lang.Throwable**. Với Java thuần, bạn có thể tự duyệt getCause().

### Tránh vòng lặp và quá nhiều tầng

Không nên mặc định mọi chuỗi đều ngắn, nhất là khi nhận Throwable từ thư viện hoặc mã tùy chỉnh. **initCause()** ngăn một Throwable tự đặt chính nó làm cause, nhưng có thể có một chuỗi tham chiếu bất thường giữa nhiều Throwable, nên một công cụ phân tích tổng quát cần giới hạn độ sâu hoặc phát hiện phần tử lặp.

Ví dụ helper duyệt an toàn, dùng danh tính đối tượng thay vì **equals()**:

~~~java
static Throwable deepestCause(Throwable error) {
    java.util.Set<Throwable> seen =
            java.util.Collections.newSetFromMap(
                    new java.util.IdentityHashMap<>());

    Throwable current = error;
    Throwable deepest = null;
    int depth = 0;

    while (current != null && depth < 64 && seen.add(current)) {
        deepest = current;
        current = current.getCause();
        depth++;
    }
    return deepest;
}
~~~

Đây là **snippet hàm tĩnh**, có thể đặt bên trong một lớp Java. Nó dùng tập hợp theo **object identity** và giới hạn 64 bước để tránh treo khi dữ liệu bất thường; nếu chuỗi có hơn 64 tầng thì kết quả chỉ là cause sâu nhất **đã được duyệt**, không nhất thiết là cuối chuỗi.

Trong nhiều ứng dụng, không cần tự viết traversal vì logging framework đã hiển thị chuỗi nguyên nhân khi nhận **Throwable** đầy đủ.

## 6. Ghi log cause chain đúng cách với JUL

Với **java.util.logging.Logger**, API nên dùng khi ghi lỗi có nguyên nhân là:

~~~java
logger.log(Level.SEVERE,
        "event=order.persist.failed requestId=" + requestId
                + " errorCode=STORAGE_ERROR",
        exception);
~~~

Đây là **snippet** giả định có biến **logger**, **requestId** và **exception** cùng các import cần thiết. Đối số thứ ba là **Throwable**, được đưa vào **LogRecord** qua **getThrown()**. Nếu Formatter phù hợp (chẳng hạn **SimpleFormatter**) được dùng, stack trace của ngoại lệ và các **Caused by** có thể được đưa vào đầu ra.

**Không nên thay bằng:**

~~~java
logger.severe("Order failed: " + exception.getMessage());
~~~

Cách này chỉ in chuỗi message. Nó thường **làm mất kiểu ngoại lệ, stack trace và chuỗi cause** trong bản ghi. Nếu exception.getMessage() là null, nội dung còn kém hữu ích hơn.

Cũng không nên:

~~~java
logger.severe("Order failed: " + exception);
~~~

Dù cách này thường có tên lớp và message trong **toString()**, nó vẫn chỉ là **chuỗi**, không gắn Throwable vào LogRecord. Muốn formatter có thể xử lý cause chain, hãy truyền **Throwable** đúng overload.

### Nên log ở tầng nào?

Một quy tắc hữu ích:

- **Tầng thấp:** ném ngoại lệ có ngữ cảnh hoặc bọc cause; tránh ghi stack trace nhiều lần rồi ném tiếp.
- **Tầng nghiệp vụ:** chuyển lỗi kỹ thuật thành lỗi có ý nghĩa theo hợp đồng nghiệp vụ nếu cần; giữ cause.
- **Ranh giới xử lý (HTTP/job/message consumer):** ghi **một bản log lỗi chính** có requestId/jobId, mã thao tác, mã lỗi và Throwable đầy đủ, ở nơi đã biết tác động cuối cùng.
- **Khi xử lý được lỗi:** có thể ghi INFO/WARNING phù hợp để phản ánh retry, fallback hoặc quyết định từ chối; không phải mọi ngoại lệ được bắt đều là SEVERE.

Nếu tầng repository log ERROR với stack trace rồi rethrow, tầng service log ERROR nữa, và Controller lại log ERROR, một lỗi có thể tạo **ba bản ghi** dễ bị đếm thành ba sự cố. Chọn trách nhiệm ghi log rõ ràng; chỉ ghi thêm ở các tầng khi có thông tin mới hoặc có nhu cầu điều tra thực sự.

### Mức log của ngoại lệ

**Level.SEVERE** thường phù hợp khi một lỗi không thể phục hồi khiến yêu cầu hoặc chức năng quan trọng thất bại. **Level.WARNING** có thể phù hợp với tình trạng suy giảm hoặc retry; **Level.INFO** có thể phù hợp với quyết định nghiệp vụ từ chối đầu vào có chủ đích. Chọn mức dựa vào **tác động và khả năng xử lý**, không dựa vào việc có Throwable hay có nhiều lớp trong chain.

## 7. Ví dụ Java 17+ có thể biên dịch và chạy độc lập

Chương trình sau mô phỏng ba tầng lỗi:

1. **Integer.parseInt("abc")** ném NumberFormatException.
2. **parseQuantity()** bọc nó thành QuantityFormatException để thể hiện lỗi định dạng nghiệp vụ.
3. **processOrder()** bọc tiếp thành OrderProcessingException để diễn đạt thao tác xử lý đơn hàng thất bại.
4. **main()** chỉ ghi log ở ranh giới cuối, truyền Throwable vào **Logger.log(Level, String, Throwable)**.

Để stdout có thể kiểm chứng, chương trình dùng một Formatter minh họa in **tên loại, message và thứ tự cause**. Formatter này **không in stack trace**; trong hệ thống thật, nên dùng formatter/encoder có hỗ trợ Throwable và stack trace phù hợp.

Lưu thành file **CauseChainDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class CauseChainDemo {
    private static final Logger LOG =
            Logger.getLogger("examples.logging.cause");

    static class QuantityFormatException extends RuntimeException {
        QuantityFormatException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static class OrderProcessingException extends RuntimeException {
        OrderProcessingException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                StringBuilder text = new StringBuilder();
                text.append(record.getLevel().getName())
                        .append(" | ")
                        .append(formatMessage(record))
                        .append('\n');

                Throwable current = record.getThrown();
                int depth = 0;
                while (current != null && depth < 10) {
                    text.append("cause[").append(depth).append("] ")
                            .append(current.getClass().getSimpleName())
                            .append(": ")
                            .append(current.getMessage())
                            .append('\n');
                    current = current.getCause();
                    depth++;
                }
                return text.toString();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        output.setLevel(Level.ALL);
        LOG.addHandler(output);
        try {
            processOrder("ORD-17", "abc");
        } catch (OrderProcessingException e) {
            LOG.log(Level.SEVERE,
                    "event=order.failed orderId=ORD-17", e);
        } finally {
            LOG.removeHandler(output);
            output.flush();
        }
    }

    private static void processOrder(
            String orderId, String quantityText) {
        try {
            int quantity = parseQuantity(quantityText);
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
        } catch (QuantityFormatException e) {
            throw new OrderProcessingException(
                    "order validation failed", e);
        }
    }

    private static int parseQuantity(String text) {
        try {
            return Integer.parseInt(text);
        } catch (NumberFormatException e) {
            throw new QuantityFormatException(
                    "quantity must be an integer", e);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac CauseChainDemo.java
java CauseChainDemo
~~~

**Stdout dự kiến của ví dụ** với JDK 17 thông dụng:

~~~text
SEVERE | event=order.failed orderId=ORD-17
cause[0] OrderProcessingException: order validation failed
cause[1] QuantityFormatException: quantity must be an integer
cause[2] NumberFormatException: For input string: "abc"
~~~

**Giải thích chi tiết:**

- **Integer.parseInt("abc")** không tạo được số nguyên nên ném NumberFormatException.
- **parseQuantity()** bắt ngoại lệ và tạo **QuantityFormatException("quantity must be an integer", e)**, nhờ đó lỗi định dạng có ngữ cảnh rõ ràng mà vẫn giữ NumberFormatException.
- **processOrder()** bọc tiếp thành **OrderProcessingException("order validation failed", e)**; đây là loại lỗi được main hiểu và bắt.
- **LOG.log(Level.SEVERE, ..., e)** đưa cả OrderProcessingException vào LogRecord. Formatter lấy ngoại lệ qua **record.getThrown()**, rồi duyệt **getCause()**.
- **cause[0]** trong ví dụ là ngoại lệ **ngoài cùng đang được log**, **cause[1]** là cause trực tiếp, **cause[2]** là cause sâu hơn. Đây là **quy ước đánh số của Formatter minh họa**, không phải cú pháp đầu ra chuẩn của JUL.
- **LOG.setUseParentHandlers(false)** tránh Handler mặc định của Logger cha xuất thêm log ra stderr. **StreamHandler(System.out, ...)** được dùng để tạo output rõ ràng trên stdout.
- Override **publish()** và gọi **flush()** giúp StreamHandler xuất mỗi sự kiện ngay thay vì phụ thuộc việc xả bộ đệm; chương trình tránh đóng Handler đã gắn với System.out.
- Thông điệp mặc định của **NumberFormatException** khi phân tích "abc" trên JDK thông dụng là **For input string: "abc"**; đây là một chi tiết từ việc phân tích số, không nên xây logic nghiệp vụ phụ thuộc nội dung message chính xác của thư viện.

Trong sản phẩm thực tế, bạn thường để SimpleFormatter hoặc backend logging thích hợp xuất stack trace đầy đủ. Chương trình trên chủ đích in chuỗi cause **rút gọn nhưng xác định** để thấy trực tiếp liên kết giữa ba lớp.

### Nếu muốn xem stack trace đầy đủ

Với cùng Throwable **e**, một cách kiểm tra trong mã học tập là:

~~~java
e.printStackTrace();
~~~

Đây là snippet đặt bên trong khối catch có biến **e**, không phải chương trình độc lập. **printStackTrace()** thường viết ra **System.err** và bao gồm stack trace của Throwable cùng các đoạn **Caused by** nếu có. Trong ứng dụng chạy thật, ưu tiên truyền Throwable cho logger thay vì gọi printStackTrace() độc lập, vì hệ thống logging có thể cần cấu hình level, định dạng, gửi tới collector và liên kết requestId.

## 8. Cause chain và stack trace: khác biệt khi điều tra

Xét một đoạn mô tả rút gọn:

~~~text
OrderProcessingException: order validation failed
    at OrderService.processOrder(...)
Caused by: QuantityFormatException: quantity must be an integer
    at QuantityParser.parse(...)
Caused by: NumberFormatException: For input string: "abc"
    at java.lang.Integer.parseInt(...)
~~~

Đây là **mẫu minh họa**, không phải stack trace nguyên văn do một lần chạy cụ thể sinh ra. Java có thể in thêm nhiều frame và các dòng rút gọn như **... N more** để tránh lặp stack frame.

Khi xem một stack trace có cause:

1. Tìm **ngoại lệ ngoài cùng** để biết thao tác nào thất bại và ở tầng nào.
2. Theo các phần **Caused by** để xác định ngoại lệ nào được bọc, bọc ở đâu.
3. Xem những frame đầu tiên thuộc **mã ứng dụng của bạn** gần nguồn lỗi để xác định điểm cần kiểm tra.
4. Kết hợp **requestId**, thời điểm, dữ liệu hợp lệ được phép ghi và log liên quan để hiểu tình huống.
5. Kiểm tra kết luận của bạn: ngoại lệ cuối chuỗi là điểm biểu hiện kỹ thuật gần nhất, nhưng nguyên nhân hệ thống có thể nằm ở cấu hình, phụ thuộc, dữ liệu hoặc các bước trước đó.

**Đừng chỉ tìm chữ “Caused by” cuối cùng rồi bỏ qua các tầng trên.** Ví dụ NumberFormatException cho biết dữ liệu không chuyển được thành số, nhưng lớp nghiệp vụ mới cho biết trường đó được dùng để xác thực số lượng đơn hàng. Cả hai đều cần để phân biệt lỗi do client và lỗi do ứng dụng tạo dữ liệu sai.

## 9. Cause khác suppressed exception như thế nào?

Trong Java, **suppressed exception** không nằm trong chuỗi getCause(). Nó được lưu dưới một danh sách riêng, lấy bằng **Throwable.getSuppressed()**.

Trường hợp tiêu biểu là **try-with-resources**:

~~~java
try (java.io.BufferedReader reader =
        new java.io.BufferedReader(
                new java.io.StringReader("sample"))) {
    // Đọc dữ liệu; có thể phát sinh lỗi trong thân try.
}
~~~

Đoạn trên chỉ minh họa cú pháp try-with-resources; BufferedReader dùng với StringReader thông thường không tự tạo lỗi khi đóng. Trong một trường hợp có tài nguyên lỗi ở **close()** đồng thời thân try đã ném ngoại lệ, Java có thể giữ lỗi từ close() dưới dạng **suppressed** gắn vào ngoại lệ chính, thay vì thay thế ngoại lệ chính.

Mô hình có thể là:

~~~text
PrimaryException
  |
  +-- getCause()           -> RootCause (nếu có)
  |
  +-- getSuppressed()[0]   -> CloseFailureA
  +-- getSuppressed()[1]   -> CloseFailureB
~~~

Vì thế:

- **getCause()**: đi sâu theo *chuỗi nguyên nhân*.
- **getSuppressed()**: lấy những Throwable được giữ lại ở dạng *lỗi bị nén*; có thể có nhiều phần tử.
- **printStackTrace()** của Java có thể thể hiện cả **Caused by** và **Suppressed**, với cấu trúc thụt lề khác nhau.
- Một bộ phân tích chỉ duyệt **getCause()** sẽ **không nhìn thấy suppressed exceptions**. Khi các lỗi đóng tài nguyên quan trọng, dùng formatter hoặc công cụ logging có khả năng xuất đầy đủ Throwable.

Không tự biến mọi suppressed exception thành một cause mới: làm vậy có thể sai ngữ nghĩa của lỗi chính và bỏ mất các lỗi bị nén khác.

## 10. Cause chain qua nhiều lớp và qua nhiều dịch vụ

### Trong cùng một JVM

Cause chain hoạt động khi các lớp truyền trực tiếp đối tượng Throwable qua lời gọi hoặc khi lớp trên bọc ngoại lệ của lớp dưới. Ví dụ:

~~~text
Repository/Parser  -> NumberFormatException
Domain/Service     -> QuantityFormatException(cause=NumberFormatException)
Application        -> OrderProcessingException(cause=QuantityFormatException)
HTTP boundary      -> log Throwable, chuyển thành response phù hợp
~~~

Đây là đường đi minh họa. Không phải mọi lỗi đều cần đủ bốn tầng và không phải API nào cũng nên trả chi tiết nội bộ cho client.

### Qua HTTP/message queue hoặc ranh giới tiến trình

Đối tượng Throwable Java **không tự đi qua** REST/JSON, message broker hoặc các ngôn ngữ khác thành một cause chain liên tục. Thông thường, dịch vụ nhận có thể nhận **HTTP status, errorCode, response message và correlation ID**, rồi tạo ngoại lệ cục bộ, ví dụ **RemoteServiceException**, mô tả tác động với dịch vụ hiện tại.

Nếu cần truy tìm nguồn lỗi xuyên dịch vụ:

- Dùng **correlationId/traceId** nhất quán ở các dịch vụ liên quan.
- Log Throwable tại **dịch vụ phát sinh** với dữ liệu được phép lưu.
- Truyền mã lỗi và thông tin giao thức phù hợp, tránh lộ stack trace hoặc thông điệp nhạy cảm ra ngoài.
- Kết hợp **tracing** và log từng dịch vụ để xác định chuỗi nguyên nhân cấp hệ thống.

Đừng gán giả rằng một ngoại lệ trong dịch vụ A phải xuất hiện nguyên vẹn qua **getCause()** trong JVM của dịch vụ B nếu giao thức chưa hỗ trợ truyền thông tin như vậy.

## 11. Khi nào nên bọc, ném lại, xử lý hoặc ghi log?

| Tình huống | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Ngoại lệ đã đúng loại và ngữ nghĩa tầng hiện tại | throw e; nếu hợp đồng cho phép | Không tạo lớp cause thừa |
| Muốn chuyển lỗi thư viện thành lỗi nghiệp vụ rõ nghĩa | new DomainException(message, e) | Giữ nguyên nhân gốc và bổ sung ngữ cảnh |
| Lỗi được xử lý hoàn toàn bằng fallback | Xử lý và ghi sự kiện phù hợp nếu cần | Không tạo cảm giác request thất bại khi đã phục hồi |
| Lỗi phải lan đến HTTP/job boundary | Bọc nếu cần rồi rethrow | Một nơi cuối ghi log với thông tin tổng thể |
| Ranh giới cuối xác nhận thao tác thất bại | logger.log(level, context, e) | Có thông điệp, mã lỗi, stack trace và cause |
| Lỗi được định nghĩa là kết quả hợp lệ, ví dụ dữ liệu sai | Trả kết quả/exception theo hợp đồng; log INFO nếu hữu ích | Không phải mọi từ chối là sự cố SEVERE |

**Đặt trách nhiệm rõ ràng:** lớp dưới tạo và bảo toàn nguyên nhân; lớp biên biết kết quả cuối cùng và có thể log. Nếu service bắt rồi log SEVERE nhưng controller vẫn retry thành công, dòng log SEVERE ban đầu có thể gây cảnh báo sai.

Trong xử lý bất đồng bộ, một ngoại lệ có thể được bọc bởi **ExecutionException** (lấy kết quả Future) hoặc **CompletionException** (một số đường hoàn tất CompletableFuture), tùy API và cách gọi. Khi điều tra, theo **getCause()** để xem lỗi tác vụ, nhưng vẫn giữ wrapper nếu nó chứa thông tin hữu ích về cách lỗi được chuyển qua cơ chế bất đồng bộ.

## 12. Gắn ngữ cảnh cho log lỗi mà không làm mất cause

Cause chain cho biết **ngoại lệ nào dẫn tới ngoại lệ nào**; nó thường chưa đủ để biết yêu cầu hay đơn hàng cụ thể nào bị ảnh hưởng. Một bản ghi lỗi tốt nên có:

- **event** ổn định: ví dụ order.persist.failed.
- **requestId/jobId** để nối log cùng luồng xử lý.
- **operation** và **errorCode** có thể tìm kiếm.
- **service/component** phát log; có thể có tên phụ thuộc liên quan.
- **Throwable đầy đủ** truyền vào logging API, không cắt ở getMessage().
- **outcome** hoặc trạng thái cuối của tác vụ nếu cần phân biệt với retry đã phục hồi.

Ví dụ minh họa dạng JSON, **không phải định dạng mặc định của JUL**:

~~~json
{
  "level": "SEVERE",
  "event": "order.persist.failed",
  "service": "order-service",
  "requestId": "req-42",
  "orderId": "ORD-17",
  "errorCode": "INVALID_QUANTITY",
  "exceptionType": "OrderProcessingException",
  "causeTypes": [
    "QuantityFormatException",
    "NumberFormatException"
  ]
}
~~~

Một formatter thực tế có thể bổ sung stack trace hoặc trường mô tả Throwable, nhưng cần cân nhắc chi phí và dữ liệu nhạy cảm. Ví dụ trên chỉ minh họa cách tách **các trường tìm kiếm được** khỏi **chi tiết ngoại lệ**.

**Bảo mật:** exception message của thư viện có thể chứa đường dẫn file, SQL, endpoint, token, mẩu dữ liệu đầu vào hoặc thông tin cá nhân. Không log mọi thông điệp thô vào kênh không phù hợp. Kiểm soát quyền đọc, retention, redaction và encoder. Không trả cause chain và stack trace nội bộ cho client ngoài môi trường tin cậy.

## 13. Chi phí và giới hạn của việc ghi đầy đủ cause chain

Ghi stack trace dài có ích khi điều tra lỗi, nhưng chi phí có thể đáng kể:

- **Dung lượng:** nhiều wrapper và stack trace dài làm một sự kiện trở thành hàng chục hoặc hàng trăm dòng.
- **Hiệu năng:** tạo và format stack trace có chi phí CPU, bộ nhớ, I/O; log ở vòng lặp retry có thể làm tình hình xấu hơn.
- **Khả năng đếm sự cố:** cùng lỗi được ghi ở nhiều tầng làm tăng số event không đúng thực tế.
- **Tìm kiếm:** nếu formatter biến stack trace thành chuỗi nhiều dòng không được collector gộp đúng, hệ thống log có thể chia một ngoại lệ thành nhiều bản ghi.
- **Dữ liệu riêng tư:** thông điệp nguyên nhân có thể mang dữ liệu không nên lưu dài hạn.

Vì vậy, nên ghi stack trace đầy đủ ở **vị trí và mức log phù hợp**, giữ context/tracing nhất quán, hạn chế lặp lại cùng Throwable qua retry, và thiết lập pipeline hỗ trợ multiline hoặc structured exception fields. Đừng cắt bỏ cause chỉ để giảm dung lượng: chọn chính sách log phù hợp với từng đích và dùng metric/tổng hợp để quan sát tần suất cao.

## 14. Sai lầm thường gặp với Cause chain

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| throw new DomainException(e.getMessage()) | Mất Throwable gốc | Dùng constructor nhận cause |
| logger.severe(e.getMessage()) | Mất loại lỗi, stack trace, cause | Dùng logger.log(Level, message, e) |
| Bọc ở mọi tầng mà không thêm ngữ cảnh | Chuỗi dài và khó đọc | Chỉ bọc khi đổi ngữ nghĩa/trách nhiệm |
| Ghi stack trace ở repository, service và controller | Một sự cố thành nhiều bản log | Chọn một điểm ghi lỗi chính |
| Chỉ xem ngoại lệ ngoài cùng | Không thấy nguồn lỗi thấp hơn | Kiểm tra getCause()/Caused by |
| Chỉ xem cause sâu nhất | Mất ý nghĩa nghiệp vụ và đường xử lý | Đọc cả ngoại lệ ngoài và các tầng trung gian |
| Nhầm suppressed với cause | Bỏ sót lỗi đóng tài nguyên | Kiểm tra getSuppressed() khi cần |
| Duyệt cause không có giới hạn | Có thể treo ở chuỗi bất thường | Giới hạn độ sâu hoặc theo dõi identity |
| Log thông điệp lỗi chứa dữ liệu người dùng thô | Lộ bí mật, log injection | Giảm dữ liệu và escape/redact phù hợp |
| Trả nguyên stack trace cho API client | Lộ cấu trúc nội bộ | Chuyển thành mã lỗi và thông điệp an toàn |
| Cho rằng cause tự truyền qua HTTP | Không kết nối được lỗi giữa dịch vụ | Dùng traceId/correlationId và log từng dịch vụ |
| Coi root cause kỹ thuật là nguyên nhân vận hành cuối cùng | Chẩn đoán thiếu bối cảnh | Kết hợp metric, tracing, cấu hình và dữ liệu hợp lệ |

## 15. Checklist khi ghi log ngoại lệ có nhiều nguyên nhân

1. Xác định **ngoại lệ gốc được bắt ở đâu** và liệu tầng này có thật sự cần bọc lại không.
2. Nếu bọc, dùng **super(message, cause)** hoặc constructor chuẩn nhận cause; không tự ý bỏ Throwable đã bắt.
3. Giữ thông điệp mỗi tầng ngắn, rõ **ngữ cảnh mới**, tránh lặp nguyên văn exception message ở mọi lớp.
4. Ở ranh giới cuối, log với **Logger.log(Level, message, Throwable)** hoặc API tương đương của framework thực tế.
5. Kiểm tra formatter/collector có xuất **stack trace và các phần Caused by** khi cần; hiểu cách nó biểu diễn **suppressed**.
6. Thêm **event, requestId/jobId, operation và errorCode** an toàn; không đưa bí mật hoặc toàn bộ payload vào log.
7. Chỉ ghi lỗi ở những điểm có mục đích rõ; không nhân đôi stack trace giữa các tầng.
8. Phân biệt **lỗi kỹ thuật**, **kết quả từ chối hợp lệ** và **retry đã phục hồi** khi chọn INFO/WARNING/SEVERE.
9. Với xử lý đồng thời hoặc đa dịch vụ, truyền correlation context và dùng tracing/log liên kết; không dựa riêng vào thứ tự dòng.
10. Thử một trường hợp thực sự ném ngoại lệ, đọc lại log và kiểm tra thấy **ngoại lệ ngoài cùng, từng cause, bước lỗi và tác động nghiệp vụ**.

**Kết luận:** Cause chain giữ quan hệ **“ngoại lệ này do ngoại lệ nào gây ra”** khi lỗi đi qua các tầng Java. Bảo toàn cause bằng constructor nhận Throwable và ghi log **kèm Throwable** cho phép điều tra từ tác động nghiệp vụ tới lỗi kỹ thuật mà không đánh mất ngữ cảnh.
