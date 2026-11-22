# Exception và log level trong Java

## 1. Mô hình tư duy: ngoại lệ xảy ra không đồng nghĩa phải ghi ERROR

Trong Java, **exception (ngoại lệ)** là cơ chế báo hiệu một tình huống làm luồng xử lý thông thường bị gián đoạn. **Log level (mức log)** là cách ứng dụng mô tả mức độ đáng chú ý của một sự kiện với người vận hành. Hai khái niệm liên quan nhưng không tương đương.

Ví dụ, cùng là `IOException` khi đọc một tệp:

- Tệp cấu hình **bắt buộc** không thể đọc lúc khởi động, khiến ứng dụng không chạy được: sự cố nghiêm trọng, thường cần `SEVERE` của `java.util.logging` hoặc `ERROR` của SLF4J.
- Tệp **tùy chọn** không tồn tại và ứng dụng đã áp dụng giá trị mặc định đúng thiết kế: có thể ghi `INFO`, `FINE`, hoặc không cần log.
- Tệp tạm không đọc được, ứng dụng thử lại có kiểm soát và đã có phương án phục hồi: mức `WARNING` hoặc thấp hơn tùy mức độ bất thường và chính sách vận hành.

Cùng **loại exception**, nhưng hậu quả đối với nghiệp vụ khác nhau. Ngược lại, một tình trạng nghiệp vụ không phát sinh exception (ví dụ trạng thái dữ liệu vi phạm ràng buộc quan trọng) vẫn có thể cần ghi `SEVERE`.

**Nguyên tắc trung tâm:** chọn mức log dựa trên *điều gì đã xảy ra, có được dự kiến không, tác động ra sao, có phục hồi được không và có cần ai hành động không*. Không chọn mức chỉ bằng tên lớp exception hoặc chỉ vì code đi vào nhánh `catch`.

Cần phân biệt thêm ba câu hỏi:

1. **Xử lý ngoại lệ thế nào?** Phục hồi, trả kết quả, thử lại, chuyển thành exception khác hay tiếp tục ném ra ngoài?
2. **Ghi sự kiện gì?** Có đủ thông tin để chẩn đoán, mã ngữ cảnh và nguyên nhân không?
3. **Ghi ở mức nào và tại ranh giới nào?** Ai là người chịu trách nhiệm đưa ra kết luận về sự cố và tránh ghi lặp?

Logging giúp quan sát; nó **không bắt hoặc xử lý ngoại lệ thay cho `try/catch`**. Việc gọi `logger.log(Level.SEVERE, ...)` cũng không tự làm chương trình dừng, rollback giao dịch hay trả HTTP 500.

## 2. Các nhóm exception và mức log

Trong Java, `Throwable` là lớp cha của `Exception` và `Error`. Những nhóm thường gặp:

| Nhóm | Ví dụ | Điều cần hiểu |
| --- | --- | --- |
| Checked exception | `IOException`, `SQLException` | Trình biên dịch yêu cầu bắt hoặc khai báo `throws` trong các trường hợp tương ứng; không mặc định nghiêm trọng |
| Unchecked exception | `IllegalArgumentException`, `IllegalStateException`, `NullPointerException` | Không bắt buộc khai báo `throws`; mức log vẫn phụ thuộc bối cảnh |
| `Error` | `OutOfMemoryError`, `StackOverflowError` | Thường báo hiệu vấn đề nghiêm trọng ở mức JVM/hạ tầng; không nên thiết kế luồng nghiệp vụ thông thường dựa vào việc bắt và tiếp tục |
| Ngoại lệ nghiệp vụ tự định nghĩa | `OrderAlreadyCancelledException`, `CreditLimitExceededException` | Có thể biểu thị kết quả dự kiến; có cần log và ở mức nào là quyết định nghiệp vụ/vận hành |

Ví dụ, `IllegalArgumentException` do người dùng cung cấp một lựa chọn không hợp lệ đã được nhận diện và trả thông báo 400 phù hợp có thể là một tình huống bình thường. Nhưng `IllegalArgumentException` xuất hiện do code nội bộ truyền sai tham số, làm hỏng một giao dịch quan trọng, có thể là lỗi nghiêm trọng. Không có quy tắc `RuntimeException == ERROR` hay `checked Exception == WARNING`.

Bản ghi log cũng không phải exception. Trong JUL, một `LogRecord` có thể mang thông điệp, mức log và **tham chiếu đến `Throwable`** bằng `getThrown()`. Một bản ghi `INFO` hoàn toàn có thể không có exception, và một bản ghi `SEVERE` có thể mô tả tình trạng lỗi mà chưa có đối tượng `Throwable` cụ thể.

## 3. Các mức log trong Java: gọi đúng tên API

### `java.util.logging` (JUL) của JDK

Các mức thường gặp, từ mức nghiêm trọng/đáng chú ý cao đến thông tin chẩn đoán chi tiết:

| JUL | Ý nghĩa thực tế thường dùng | Ví dụ |
| --- | --- | --- |
| `SEVERE` | Lỗi nghiêm trọng; thao tác/dịch vụ không hoàn thành hoặc không thể tiếp tục an toàn | Hết lần thử mà nghiệp vụ thất bại; không mở được tài nguyên bắt buộc lúc khởi động |
| `WARNING` | Bất thường cần chú ý; hệ thống có thể phục hồi/đang suy giảm hoặc cần theo dõi | Hệ thống dùng phương án dự phòng; một dịch vụ phụ tạm mất kết nối |
| `INFO` | Sự kiện vận hành/nghiệp vụ đáng ghi nhưng diễn ra trong luồng bình thường | Một yêu cầu không hợp lệ được từ chối đúng quy tắc |
| `CONFIG` | Thông tin cấu hình | Bật/tắt tính năng hoặc xác nhận giá trị cấu hình không nhạy cảm |
| `FINE`, `FINER`, `FINEST` | Thông tin chẩn đoán ngày càng chi tiết | Một bước kiểm tra nội bộ, trạng thái phục vụ điều tra |
| `OFF`, `ALL` | Các mức đặc biệt phục vụ bật/tắt ngưỡng lọc | `ALL` không phải mức biểu thị một sự cố |

Trong JUL **không có hằng `Level.ERROR`, `Level.WARN` hoặc `Level.DEBUG`**. Để ghi lỗi nghiêm trọng theo JUL, sử dụng `Level.SEVERE`. Tên và ngữ nghĩa chi tiết có thể khác giữa các hệ thống logging.

### SLF4J với Logback hoặc implementation tương ứng

Các mức thông dụng của API SLF4J là `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE`. Thông thường:

- `ERROR`: hoạt động quan trọng thất bại, cần điều tra hoặc hành động.
- `WARN`: bất thường có khả năng ảnh hưởng hệ thống, có thể còn khôi phục.
- `INFO`: diễn biến bình thường có ý nghĩa với vận hành.
- `DEBUG`, `TRACE`: chi tiết kỹ thuật cho điều tra.

Đây là **quy ước vận hành**, không phải tiêu chuẩn Java bắt buộc ứng dụng phải đặt mức giống hệt nhau. Một số hệ thống như Log4j 2 còn hỗ trợ `FATAL`, nhưng không nên tự giả định mọi API đều có mức này.

**Không đánh đồng giá trị mức của các framework.** Mẫu code JUL `LOG.log(Level.SEVERE, "...", e)` có vai trò tương tự `LOG.error("...", e)` trong SLF4J, nhưng cách cấu hình, mức lọc, định dạng và API khác nhau.

## 4. Cách quyết định level khi có exception

Hãy lần lượt hỏi:

1. **Tình huống có dự kiến trong quy trình không?** Ví dụ nhập sai thông tin, giới hạn tín dụng không đủ hoặc hủy một yêu cầu đã hoàn tất có thể là kết quả bình thường.
2. **Bước nghiệp vụ có hoàn thành theo cam kết không?** Nếu không, đây là thất bại cần phân loại rõ.
3. **Hệ thống có phục hồi thành công không?** Có fallback, retry hay luồng thay thế bảo toàn được yêu cầu không?
4. **Mức độ ảnh hưởng và phạm vi?** Một dữ liệu tùy chọn bị thiếu khác với mất cơ sở dữ liệu cốt lõi.
5. **Ai cần phản ứng với bản ghi này?** Nếu alert theo mức lỗi, `ERROR` trên những trường hợp dự kiến tạo ra nhiều cảnh báo giả.
6. **Sự kiện đã được ghi ở nơi nào khác chưa?** Một exception bị ném qua nhiều tầng không nên tạo nhiều dòng `ERROR` giống nhau.

Một bảng quyết định tham khảo:

| Tình huống | Xử lý | Mức thường hợp lý | Ghi chú |
| --- | --- | --- | --- |
| Dữ liệu đầu vào không hợp lệ và đã trả phản hồi đúng thiết kế | Từ chối hợp lệ | `INFO`/`FINE` hoặc không ghi | Không ghi stack trace cho từng lỗi người dùng thông thường |
| Hết hạn thẻ, không đủ số dư | Quyết định nghiệp vụ dự kiến | `INFO` nếu cần theo dõi | Dùng `reason_code` ổn định |
| Cache bị lỗi nhưng đọc trực tiếp DB thành công | Phục hồi qua fallback | `WARNING` khi đây là dấu hiệu bất thường | Có thể chỉ dùng DEBUG/metric nếu tình trạng quá phổ biến và đã được đo riêng |
| Gọi gateway timeout một lần, đã lên lịch retry | Chưa kết luận thất bại cuối | `WARNING` hoặc `INFO` tùy mức độ bất thường | Dùng attempt/operation id, tránh alert cho từng retry nhỏ |
| Gateway hết toàn bộ lần thử, yêu cầu thanh toán thất bại | Không phục hồi | `SEVERE` / `ERROR` tại điểm kết luận | Ghi một lần kèm nguyên nhân gốc và mã tương quan |
| Không tìm thấy file cấu hình **tùy chọn**, dùng mặc định | Hoạt động tiếp đúng chính sách | `INFO`/`CONFIG`/`FINE` | Không suy diễn `FileNotFoundException` luôn là ERROR |
| Không đọc được cấu hình **bắt buộc**, dừng khởi động | Không thể phục vụ | `SEVERE` / `ERROR` | Thường là lỗi cần xử lý |
| Request bị hủy theo yêu cầu hoặc shutdown hợp lệ | Kết thúc dự kiến | `FINE`/`INFO` hoặc không ghi | Đặc biệt thận trọng với `InterruptedException` |
| Lỗi logic làm mất kết quả một tác vụ quan trọng | Thất bại ngoài dự kiến | `SEVERE` / `ERROR` | Giữ exception và đủ ngữ cảnh để tìm lỗi |

Những đề xuất trên cần được điều chỉnh theo mức dịch vụ cam kết, số lượng sự kiện và quy định cảnh báo. Một ngoại lệ hiếm nhưng được xử lý hoàn toàn cũng có thể cần `WARNING`; một retry trong cơ chế bình thường rất nhiều lần lại có thể chỉ cần `FINE` cùng metric tổng hợp.

## 5. Ví dụ Java 17+ chạy được: INFO, WARNING, SEVERE với Throwable

Chương trình minh họa ba hoàn cảnh và cho phép quan sát rõ chúng khác nhau:

- Đơn hàng thiếu mã được **từ chối theo quy tắc**: ghi `INFO`, không tạo exception vô ích.
- Cổng thanh toán mô phỏng bị timeout nhưng sẽ được thử lại: ghi `WARNING` với `IOException` đi kèm.
- Kho hóa đơn bắt buộc bị lỗi và tác vụ không thể hoàn tất: ghi `SEVERE` với `IllegalStateException`.

Chương trình dùng `java.util.logging` của JDK; để đầu ra chính xác và ngắn gọn, bộ định dạng chỉ in lớp và thông điệp của exception. **`LogRecord` vẫn mang `Throwable`**, nhưng formatter này **không in toàn bộ stack trace**. Phần sau sẽ chỉ ra cách in đầy đủ khi cần điều tra thực tế.

Tạo tệp **`ExceptionLogLevelDemo.java`** với nội dung:

```java
import java.io.IOException;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ExceptionLogLevelDemo {
    private static final Logger LOG =
            Logger.getLogger(ExceptionLogLevelDemo.class.getName());

    private ExceptionLogLevelDemo() {
    }

    private static void setupLogging() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String result = record.getLevel().getName()
                        + " " + formatMessage(record);
                Throwable cause = record.getThrown();
                if (cause != null) {
                    result += " exception="
                            + cause.getClass().getSimpleName()
                            + " detail=" + cause.getMessage();
                }
                return result + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);
    }

    private static void rejectInvalidOrder() {
        LOG.info("event=order_rejected reason_code=EMPTY_ORDER_ID");
    }

    private static void schedulePaymentRetry() {
        try {
            throw new IOException("gateway timeout");
        } catch (IOException e) {
            LOG.log(Level.WARNING,
                    "event=payment_gateway_timeout action=retry_scheduled",
                    e);
        }
    }

    private static void failRequiredInvoiceStep() {
        try {
            throw new IllegalStateException("invoice store unavailable");
        } catch (IllegalStateException e) {
            LOG.log(Level.SEVERE,
                    "event=invoice_generation_failed action=abort",
                    e);
        }
    }

    public static void main(String[] args) {
        setupLogging();

        rejectInvalidOrder();
        schedulePaymentRetry();
        failRequiredInvoiceStep();

        LOG.fine("event=diagnostic_detail message=hidden");
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ExceptionLogLevelDemo.java
java ExceptionLogLevelDemo
```

**Kết quả stderr** (vì `ConsoleHandler` của JUL mặc định ghi vào `System.err`):

```text
INFO event=order_rejected reason_code=EMPTY_ORDER_ID
WARNING event=payment_gateway_timeout action=retry_scheduled exception=IOException detail=gateway timeout
SEVERE event=invoice_generation_failed action=abort exception=IllegalStateException detail=invoice store unavailable
```

**Kết quả stdout:** không có dòng nào. Terminal thường hiển thị cả hai luồng, nên vẫn nhìn thấy các dòng stderr trên màn hình.

### Những điều cần quan sát

- `rejectInvalidOrder()` không ném ngoại lệ; mức log phản ánh **kết quả nghiệp vụ**, không phụ thuộc có `Throwable` hay không.
- `schedulePaymentRetry()` và `failRequiredInvoiceStep()` đều có exception, nhưng mức khác nhau vì tình trạng phục hồi và ảnh hưởng khác nhau.
- `LOG.log(Level.WARNING, "...", e)` dùng overload có tham số `Throwable`; `record.getThrown()` trong formatter vẫn lấy lại được object exception.
- `LOG.fine(...)` không xuất hiện vì logger và handler đều đặt mức `INFO`. Bật `FINE` tại logger **và** handler nếu thực sự muốn thấy bản ghi này.
- `LOG.setUseParentHandlers(false)` tránh chuyển thêm log lên handler của logger cha trong ví dụ, nhờ vậy không có bản sao ngoài những dòng đã dự đoán.
- Code ở `failRequiredInvoiceStep()` **bắt exception và chỉ ghi log**, nên chương trình vẫn chạy hết `main`. Đây là ví dụ quan sát log; ứng dụng thật khi bước bắt buộc thất bại còn phải **trả trạng thái thất bại, dừng, rollback hoặc ném lại** theo hợp đồng nghiệp vụ. Một dòng `SEVERE` tự nó không tạo ra những hành vi ấy.

### Vì sao không dùng stack trace đầy đủ ở ví dụ?

Nếu dùng formatter thông thường, số dòng và phần đầu của stack trace có thể phụ thuộc vị trí code, thời gian, thread và cấu hình. Ví dụ kiểm soát formatter để kết quả rõ và dễ tái hiện. **Không coi cách bỏ stack trace ở đây là khuyến nghị mặc định cho production**: lỗi không mong đợi thường cần stack trace (và cause chain) để tìm vị trí phát sinh.

## 6. Ghi exception đúng API để giữ thông tin chẩn đoán

Với JUL, cách nên dùng khi muốn giữ exception là:

```java
try {
    performCriticalOperation();
} catch (IOException e) {
    LOG.log(Level.SEVERE, "event=operation_failed", e);
    throw new IllegalStateException("Critical operation failed", e);
}
```

Đây là **đoạn minh họa trong một lớp**, yêu cầu `LOG` và `performCriticalOperation()` đã được khai báo; nó không phải tệp có thể chạy độc lập. Đoạn code thể hiện overload `Logger.log(Level, String, Throwable)`. Ở một ứng dụng nhiều lớp, **không nhất thiết nên vừa log `SEVERE` vừa ném lại** như ví dụ cú pháp này: nếu tầng ngoài cũng log sẽ gây trùng. Phần sau giải thích cách chọn ranh giới ghi log.

Cách dễ mất thông tin:

```java
// Chỉ ghi chuỗi, mất Throwable trong bản ghi:
LOG.severe("operation failed: " + e.getMessage());

// Chỉ ghi toString(), không tạo stack trace:
LOG.warning("operation failed: " + e);
```

Hai cách trên có thể cho biết tên ngoại lệ hoặc thông điệp, nhưng `LogRecord.getThrown()` sẽ không được gán exception từ chúng. Vì thế formatter/encoder có thể **không có đối tượng Throwable để in stack trace và chuỗi nguyên nhân**.

Với JUL, một lựa chọn tiêu chuẩn khi cần xem stack trace là `java.util.logging.SimpleFormatter`, ví dụ:

```java
ConsoleHandler handler = new ConsoleHandler();
handler.setFormatter(new java.util.logging.SimpleFormatter());
```

Đây là đoạn cấu hình minh họa. `SimpleFormatter` có thể in thời gian, nguồn phát, thông điệp và stack trace của `LogRecord` có `Throwable`; đầu ra cụ thể có thể chịu ảnh hưởng cấu hình và thời điểm chạy. Nó không được mô tả bằng một chuỗi stdout cố định ở đây.

### Phân biệt ba mức thông tin trong exception

| Thông tin | Lấy từ đâu | Giá trị |
| --- | --- | --- |
| **Loại exception** | `e.getClass()` hoặc `e.toString()` | Phân loại sơ bộ |
| **Thông điệp exception** | `e.getMessage()` | Một phần bối cảnh lỗi, có thể `null` hoặc chứa dữ liệu không an toàn |
| **Stack trace và cause chain** | `Throwable` truyền qua logger, formatter/encoder xử lý | Giúp lần theo đường gọi và lỗi gốc khi cần điều tra |

Đừng chỉ dựa vào `getMessage()` để chẩn đoán. Nguyên nhân chính đôi khi nằm trong `e.getCause()` hoặc một exception lồng sâu hơn. Khi chuyển ngoại lệ giữa các tầng, giữ cause:

```java
try {
    readFromGateway();
} catch (IOException e) {
    throw new IllegalStateException("Cannot complete order", e);
}
```

Đây là ví dụ không độc lập. Constructor `IllegalStateException(String, Throwable)` giữ `IOException` làm cause; nếu bỏ tham số `e`, thông tin gốc sẽ khó truy vết hơn.

## 7. Một exception đi qua nhiều tầng: log ở đâu?

Một luồng xử lý có thể gồm:

```text
HTTP Controller
    |
    v
OrderService
    |
    v
PaymentGatewayClient
    |
    X  IOException / timeout
```

Nếu `PaymentGatewayClient`, `OrderService` và `Controller` đều thực hiện:

```java
LOG.log(Level.SEVERE, "payment failed", e);
throw e;
```

thì **cùng một thất bại** có thể tạo ba bản ghi lỗi với stack trace gần giống nhau. Hậu quả là log nhiễu, chi phí tăng và cảnh báo đếm sai số lần giao dịch thất bại.

Thay vào đó, hãy xác định **ranh giới chịu trách nhiệm**:

- **Tầng hạ tầng/client:** có thể bổ sung ngữ cảnh hoặc chuyển sang ngoại lệ phù hợp và **giữ cause**. Không buộc phải ghi mức `SEVERE` nếu tầng trên sẽ quyết định kết quả.
- **Tầng dịch vụ:** nếu phục hồi hoàn toàn, ghi sự kiện fallback/retry có ý nghĩa ở mức phù hợp; nếu không thể phục hồi, ném ngoại lệ kèm ngữ cảnh để tầng xử lý cuối quyết định.
- **Tầng biên** như HTTP exception handler, job runner, message consumer: thường là nơi biết một request/job đã **thất bại cuối cùng** hay được xử lý; ghi một log lỗi có đủ `request_id`, `order_id`, `operation_id` và exception khi thực sự cần.
- **Hạ tầng giám sát:** dùng metric và trace để theo dõi tần suất/lưu lượng; tránh ghi trùng stack trace chỉ nhằm tăng độ “thấy được” của lỗi.

Quy tắc “**log hoặc ném tiếp**” là một hướng dẫn giúp tránh log trùng, không phải lệnh cấm tuyệt đối. Có thể log một **sự kiện khác có giá trị độc lập** ở tầng dưới (ví dụ “đã lên lịch retry”) và vẫn ném ngoại lệ cuối lên trên. Khi đó phải phân biệt rõ tên sự kiện và kết quả để không biến hai bản ghi thành hai lần thất bại tương đương.

### Ví dụ xử lý retry hợp lý

Giả sử một phép gọi mạng thất bại ở lần thử đầu nhưng thành công ở lần sau. Có thể có:

```text
WARNING event=dependency_unavailable attempt=1 action=retry
INFO event=payment_completed attempts=2 outcome=SUCCESS
```

Đây là log minh họa, không phải đầu ra của chương trình Java ở phần 5. Đừng ghi `SEVERE payment_failed` cho lần đầu nếu nghiệp vụ cuối cùng đã thành công; nếu retry thất bại hết và yêu cầu không thể phục hồi, khi đó ghi **sự kiện thất bại cuối** ở mức tương ứng.

Trong dịch vụ có lưu lượng cao, thậm chí mức `WARNING` cho mỗi lần retry có thể quá ồn. Có thể giảm mức log hoặc ghi một cảnh báo tổng hợp và theo dõi số lần retry qua metric; chọn dựa trên nhu cầu vận hành cụ thể.

## 8. Cách hiểu `catch`, `throw` và log level

Đoạn code dưới đây **bắt và phục hồi**:

```java
try {
    return readOptionalConfig();
} catch (IOException e) {
    LOG.log(Level.INFO,
            "event=optional_config_unavailable action=use_defaults",
            e);
    return defaultConfig();
}
```

Nếu việc dùng giá trị mặc định là tình huống thường xuyên và không cần stack trace, có thể bỏ `e` hoặc dùng mức `FINE`; nếu cấu hình không sẵn sàng là dấu hiệu suy giảm đáng theo dõi, có thể dùng `WARNING`. Chọn mức theo ý nghĩa vận hành.

Đoạn code dưới đây **chỉ đổi loại exception, rồi chuyển lên**:

```java
try {
    return callGateway();
} catch (IOException e) {
    throw new PaymentUnavailableException(
            "Gateway could not be reached", e);
}
```

Vì tầng này chưa biết request cuối cùng thất bại hay được retry/fallback ở trên, **không nhất thiết ghi `ERROR` tại đây**. Tầng biên có thể ghi đúng một lần khi biết kết quả. `PaymentUnavailableException` là tên lớp ngoại lệ giả định, cần khai báo trong dự án; đoạn code không độc lập.

Đoạn code dưới đây **nuốt exception**:

```java
try {
    chargePayment();
} catch (IOException e) {
    LOG.log(Level.SEVERE, "payment failed", e);
}
// Code tiếp tục như thể thanh toán thành công.
```

Đây là lỗi kiểm soát luồng nếu thanh toán là bước bắt buộc. **Việc đã log `SEVERE` không khiến code phía sau biết thao tác thất bại.** Cần trả kết quả không thành công, áp dụng retry/fallback được thiết kế hoặc ném ngoại lệ phù hợp; không lấy logging làm phương thức xử lý lỗi.

## 9. Lọc cấp log: logger, handler/appender và hệ thống thu thập

Một lời gọi `LOG.log(Level.FINE, "...", e)` không bảo đảm người vận hành sẽ thấy bản ghi. Trong JUL, việc ghi được kiểm tra ít nhất ở logger và từng handler:

```text
Logger level: INFO
    |
    +-- INFO     -> được phép đi tiếp
    +-- WARNING  -> được phép đi tiếp
    +-- SEVERE   -> được phép đi tiếp
    +-- FINE     -> bị loại tại logger
    |
    v
Handler level: WARNING
    |
    +-- INFO     -> bị loại tại handler
    +-- WARNING  -> tới formatter/đích
    +-- SEVERE   -> tới formatter/đích
```

Hệ thống logging còn có thể có `Filter`, handler của logger cha, cấu hình động và bộ thu phía sau. Trong JUL, một handler có mức ngưỡng `INFO` thường nhận `INFO`, `WARNING`, `SEVERE` nếu không bị lọc bởi nơi khác. Không nên chỉ nhìn mỗi `logger.setLevel(Level.FINE)` rồi kết luận `FINE` chắc chắn đến file/console; **handler cũng phải chấp nhận**.

Trong SLF4J/Logback hoặc các backend khác, các mức `DEBUG`/`INFO`/`WARN`/`ERROR` và cơ chế appender/filter có quy tắc riêng. Cần kiểm tra cấu hình thực tế thay vì dịch tên mức một cách máy móc.

**Mức log không phải cơ chế ưu tiên giao dịch.** Việc hạ/tăng level không nên thay đổi luồng xử lý lỗi hay trạng thái đơn hàng. Log bị tắt vẫn phải giữ nguyên kết quả nghiệp vụ. Nếu code dựa vào việc một `Supplier` của logger chạy để thực hiện hành động nghiệp vụ, đó là sai thiết kế.

## 10. Khi nào cần stack trace, khi nào chỉ cần mã kết quả?

Stack trace rất có giá trị khi lỗi **ngoài dự kiến** cần sửa code hoặc cấu hình. Nhưng stack trace cho từng trường hợp **được dự kiến** có thể làm log nhiễu, tốn băng thông và gây rủi ro lộ thông tin.

| Tình huống | Nên ghi gì? |
| --- | --- |
| Người dùng nhập sai định dạng | Tên sự kiện, mã lỗi kiểm soát, mã tương quan khi cần; thường không có stack |
| Quy tắc nghiệp vụ từ chối hợp lệ | `reason_code` cố định, `outcome` và định danh đối tượng an toàn |
| Lần gọi mạng thất bại, có retry | Số lần thử, thao tác phục hồi, loại lỗi; stack khi thực sự giúp điều tra |
| Lỗi không mong đợi khiến request/job thất bại | Một bản ghi ở ranh giới phù hợp, kèm `Throwable` và ngữ cảnh đủ tìm lỗi |
| Lỗi nghiêm trọng khi khởi động | Lý do không thể phục vụ, cấu hình không nhạy cảm liên quan, `Throwable`/stack khi có |
| Thất bại đã được bộ giám sát ghi nhận đầy đủ | Cân nhắc giảm log trùng ở các tầng trung gian |

Người vận hành cần cả **bối cảnh** lẫn **nguyên nhân**. Ví dụ `NullPointerException` và stack trace giúp tìm vị trí code, nhưng nếu không biết request hoặc đối tượng bị ảnh hưởng thì việc tái hiện lỗi vẫn khó. Ngược lại, mã đơn hàng mà không có exception gốc đôi khi không đủ tìm lỗi kỹ thuật.

Một bản ghi lỗi có ý nghĩa có thể gồm:

```text
event=invoice_generation_failed
order_id=ORD-101
correlation_id=req-7a
attempt=3
outcome=FAILED
reason_code=INVOICE_STORAGE_UNAVAILABLE
exception=IOException   # minh họa tên loại lỗi
```

Các dòng trên minh họa những trường nên có, không phải đề nghị ghi mỗi trường thành một dòng. Đầu ra thực tế có thể là JSON hoặc một dòng `key=value`, với stack trace được lưu dưới dạng thuộc tính riêng hoặc phần hiển thị đã được escape.

## 11. Ném lại exception và giữ chuỗi nguyên nhân

Khi ngoại lệ từ tầng thấp được chuyển thành ngoại lệ có ý nghĩa miền nghiệp vụ, đừng bỏ cause:

```java
try {
    repository.save(order);
} catch (SQLException e) {
    throw new OrderPersistenceException(
            "Could not persist order", e);
}
```

Ví dụ minh họa dùng các lớp/biến giả định của một ứng dụng thực tế. Constructor ngoại lệ tùy biến phải nhận `Throwable cause` và gọi `super(message, cause)` hoặc cơ chế tương đương. Nếu chỉ tạo `new OrderPersistenceException("Could not persist order")` mà không giữ `e`, stack trace của nguyên nhân gốc có thể bị mất khi log tầng trên.

Một exception đôi khi đã chứa nguyên nhân bên trong (nested cause), ví dụ:

```text
OrderPersistenceException: Could not persist order
    caused by SQLException: Connection unavailable
        caused by SocketTimeoutException: Read timed out
```

Trong một formatter hỗ trợ full stack trace, cause chain giúp điều tra theo chiều sâu; không cần mỗi tầng log riêng để người vận hành “thấy” cả ba loại lỗi.

**Không ghi nguyên văn `e.getMessage()` như dữ liệu an toàn tuyệt đối.** Thông điệp từ SQL driver, HTTP client hoặc dependency có thể chứa địa chỉ nội bộ, dữ liệu đầu vào, URL chứa query, mã nhận diện hoặc chuỗi nhạy cảm. Có chính sách che/giảm dữ liệu và phân quyền tại đích log.

## 12. `InterruptedException`, hủy tác vụ và `Error`

Một số tình huống dễ bị ghi sai mức:

### `InterruptedException`

Trong các hệ thống đa luồng, interruption thường là **tín hiệu yêu cầu dừng hoặc hủy**. Khi bắt exception này trong một phương thức không thể ném lại, thông thường phải khôi phục cờ interrupt:

```java
try {
    Thread.sleep(1_000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Kết thúc công việc hoặc chuyển tín hiệu hủy lên tầng thích hợp.
    return;
}
```

Đây là đoạn bên trong phương thức trả về `void` hoặc có kiểu trả về tương thích. Nếu đang trong quá trình shutdown hợp lệ, việc bị interrupt **không tự là `SEVERE`**. Ghi hàng nghìn stack trace lỗi khi ứng dụng dừng có thể che lấp sự cố thực. Tuy nhiên, nếu interruption dẫn tới hậu quả ngoài dự kiến hoặc vi phạm cam kết, xử lý và level cần theo bối cảnh.

### Hủy theo yêu cầu

`CancellationException` hoặc các trạng thái hủy công việc có thể là kết quả bình thường. Một công việc bị hủy theo yêu cầu người dùng thường cần một sự kiện `INFO` hay `FINE` (nếu cần theo dõi), không nhất thiết `ERROR`.

### `Error` nghiêm trọng

`OutOfMemoryError`, `StackOverflowError` là trường hợp đặc biệt. Sau lỗi thiếu bộ nhớ, kể cả logging cũng có thể không hoạt động đáng tin cậy; không nên thiết kế “bắt mọi `Throwable`, ghi `SEVERE` rồi tiếp tục” như chiến lược phục hồi chung. Để ứng dụng/tiến trình được quản lý bởi cơ chế giám sát và khởi động lại phù hợp khi cần.

## 13. HTTP status không phải bảng ánh xạ trực tiếp sang log level

Trong một dịch vụ web, HTTP status là **kết quả giao thức của request**; log level là **mức độ đáng chú ý cho vận hành**.

Một số tình huống minh họa:

| Phản hồi | Tình huống | Level có thể hợp lý |
| --- | --- | --- |
| 400 | Người dùng gửi dữ liệu sai cấu trúc, đã xác thực và trả lỗi đúng thiết kế | Không ghi/`DEBUG`/`INFO` tùy chính sách |
| 404 | Không tìm thấy tài nguyên được yêu cầu | Thường không cần `ERROR` |
| 409 | Xung đột trạng thái nghiệp vụ hợp lệ | `INFO` hoặc không ghi, kèm mã nguyên nhân nếu cần |
| 429 | Giới hạn tốc độ theo chính sách | Thường thống kê bằng metric; `INFO` hoặc `WARN` tùy bất thường |
| 500 | Lỗi nội bộ ngoài dự kiến khiến request thất bại | Thường `ERROR`/`SEVERE` kèm exception tại ranh giới ghi lỗi |
| 503 | Dịch vụ phụ không sẵn sàng sau khi hết retry | Có thể `ERROR`/`SEVERE` nếu request thực sự thất bại |
| 200 | Đã fallback nhưng dịch vụ phụ đang suy giảm | Có thể cần `WARNING` dù request thành công |

Bảng này không phải quy chuẩn cứng. Ví dụ một 404 từ trình thu thập tự động thường xuyên có thể chỉ là hành vi bình thường; một loạt 404 cho tài nguyên thiết yếu sau deploy có thể chỉ ra lỗi triển khai đáng cảnh báo dựa trên metric/tần suất.

Một exception handler toàn cục không nên ghi mọi `Exception` ở `ERROR` mà không phân biệt lỗi dự kiến với lỗi không dự kiến. Nên phân loại rõ ngoại lệ miền nghiệp vụ, điều kiện xác thực, trạng thái yêu cầu và ngoại lệ hệ thống trước khi quyết định message/level.

## 14. Ví dụ với SLF4J: truyền Throwable làm đối số lỗi

Trong ứng dụng dùng SLF4J cùng backend tương thích (chẳng hạn Logback), cách ghi lỗi phổ biến là:

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(PaymentService.class);

void reportFailure(String orderId, java.io.IOException cause) {
    LOG.error("event=payment_failed order_id={}", orderId, cause);
}
```

Đây là **đoạn code minh họa bên trong `PaymentService`**, cần khai báo lớp và dependency SLF4J/backend; nó không phải tệp chạy độc lập với JDK. Đối số `cause` ở cuối được SLF4J xử lý như `Throwable` trong mẫu gọi phù hợp, cho phép backend xuất stack trace; `orderId` được gắn vào placeholder `{}`. Cú pháp này khác với JUL:

```java
LOG.log(Level.SEVERE,
        "event=payment_failed order_id=" + orderId,
        cause);
```

Đoạn JUL là ví dụ trong lớp có `LOG` và `cause` phù hợp. Đây là API `Logger.log(Level, String, Throwable)`, không có overload `LOG.severe(String, Throwable)` trong JUL. Nếu muốn giữ mẫu JUL ổn định cùng tham số lẫn Throwable, có thể xây `LogRecord` rõ ràng hoặc thêm trường có cấu trúc bằng cơ chế của backend; không tự giả định mọi overload nhận đồng thời một mảng tham số và exception.

**Lỗi hay gặp trong SLF4J:**

```java
// Không nên: chỉ chuyển exception thành văn bản message.
LOG.error("payment failed: {}", cause.getMessage());

// Thường tốt hơn ở ranh giới báo lỗi:
LOG.error("event=payment_failed", cause);
```

Ở cách thứ nhất, `cause.getMessage()` là chuỗi; backend có thể không có đối tượng `Throwable` để hiển thị stack trace. Ở cách thứ hai, backend nhận exception. Dù vậy, **một exception dự kiến** không nên bị ghi `ERROR` chỉ vì đã có sẵn biến `cause`.

## 15. Ngoại lệ và thông điệp log có cấu trúc

Một message tốt nên tách thông tin có cấu trúc khỏi câu mô tả tự do. Ví dụ một bản ghi JSON minh họa:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "ERROR",
  "service": "invoice-service",
  "event": "invoice_generation_failed",
  "order_id": "ORD-101",
  "correlation_id": "req-7a",
  "outcome": "FAILED",
  "reason_code": "INVOICE_STORAGE_UNAVAILABLE",
  "exception_type": "java.io.IOException"
}
```

Đây là **dữ liệu minh họa từ một backend giả định**, không phải đầu ra JSON của chương trình JUL trong bài.

Nên nhất quán về:

- **`event`**: tên sự kiện ổn định; cùng một loại thất bại dùng cùng một tên thay vì nhiều câu mô tả khác nhau.
- **`outcome` / `reason_code`**: mã có tập giá trị được kiểm soát, khác với `e.getMessage()` vốn có thể thay đổi theo thư viện/phiên bản.
- **`correlation_id` / `trace_id`**: giúp nối các log từ cùng một luồng xử lý; không dùng dữ liệu này như bằng chứng duy nhất của giao dịch thành công.
- **`attempt` / `operation_id`**: phân biệt các lần thử và tránh đếm nhầm một sự cố lặp lại.
- **`exception_type` / stack trace**: mô tả chẩn đoán; không thay thế các trường ý nghĩa nghiệp vụ.

Đặc biệt, **tránh tạo alert chỉ dựa vào tên exception**. Một `IOException` có thể là một retry nhỏ hoặc thất bại cuối của dịch vụ cốt lõi; event, outcome và ngữ cảnh giúp phân biệt.

Khi thiết kế hệ thống tập trung, cần phân quyền và thời hạn lưu log. Stack trace và request context có thể tiết lộ cấu trúc nội bộ; không đưa mật khẩu, token, API key, thông tin thẻ hoặc payload nhạy cảm vào log. Với dữ liệu đầu vào chứa ký tự xuống dòng, dùng encoder/escape phù hợp để tránh log injection.

## 16. Một chính sách logging exception có thể áp dụng

Đội phát triển có thể thống nhất các quy tắc sau cho một dịch vụ Java:

1. **Định nghĩa ranh giới xử lý cuối** cho HTTP request, job, event consumer và tác vụ nền. Đây là nơi biết thành công, đã phục hồi hay thất bại.
2. **Phân loại kết quả dự kiến** (validation, nghiệp vụ từ chối, hủy theo yêu cầu) và **lỗi hệ thống**. Mỗi nhóm có `event` và `reason_code` rõ ràng.
3. **Quy định mức cho kết quả cuối**: vận hành bình thường `INFO`/mức thấp hơn; suy giảm có phục hồi `WARNING` khi đáng chú ý; thất bại ngoài dự kiến của chức năng quan trọng `SEVERE`/`ERROR`.
4. **Chọn điểm log stack trace**: ưu tiên nơi quyết định trạng thái thất bại, giữ cause khi chuyển exception; tránh nhiều bản sao của cùng stack trên các tầng.
5. **Kết hợp log và metric**: theo dõi số lỗi và thời gian qua metric; dùng log có mã tương quan để điều tra từng trường hợp. Tránh kích hoạt cảnh báo trên từng retry vốn được hệ thống xử lý bình thường.
6. **Kiểm tra cấu hình lọc** ở logger, handler/appender, formatter và bộ thu: mức bị vô hiệu hóa ở một khâu có thể khiến bản ghi biến mất.
7. **Quản lý bí mật và dữ liệu**: lọc thông tin nhạy cảm, chọn mức thông tin đủ dùng, kiểm soát truy cập, retention và chi phí khi có nhiều stack trace.
8. **Thử tình huống thật**: input sai, dependency hồi phục sau retry và dependency thất bại hoàn toàn. Xác nhận log level, số dòng, thông tin nguyên nhân và kết quả xử lý đều phù hợp.

Ví dụ kiểm tra ba tình huống có ích:

```text
CASE 1: Invalid input
Expected: HTTP 400 / kết quả từ chối, không có lỗi hệ thống
Log: none / INFO theo chính sách

CASE 2: Network timeout; retry success
Expected: nghiệp vụ hoàn tất, có thể có WARNING cho lần retry
Log: sự kiện phục hồi, không có lỗi cuối cùng bị ghi trùng

CASE 3: Network timeout; retries exhausted
Expected: nghiệp vụ thất bại rõ ràng
Log: một ERROR/SEVERE ở ranh giới kết luận, giữ Throwable và context
```

## 17. Sai lầm thường gặp

- **Exception nào cũng ghi `SEVERE`/`ERROR`:** tạo cảnh báo giả với các trường hợp dự kiến; hãy đánh giá tác động và khả năng phục hồi.
- **Ghi stack trace cho mọi validation error:** vừa ồn vừa tốn chi phí; khi cần theo dõi, dùng event và reason_code.
- **Chỉ ghi `e.getMessage()`:** mất stack trace/cause chain trong bản ghi; truyền `Throwable` vào overload phù hợp khi cần.
- **Bắt rồi ghi lỗi nhưng tiếp tục như thành công:** log không xử lý lỗi. Cần cập nhật kết quả, rollback, retry hoặc ném tiếp đúng hợp đồng.
- **Vừa log rồi throw ở mọi tầng:** một exception sinh nhiều dòng `ERROR`; chọn một ranh giới có trách nhiệm.
- **Ghi `ERROR` cho lần retry đầu dù retry thành công:** alert có thể báo sai một giao dịch đã phục hồi; phân biệt lần thử với kết quả cuối.
- **Nhầm JUL `Level.SEVERE` với `Level.ERROR`:** JUL không có `Level.ERROR`; dùng đúng API đang có.
- **Nhầm mức ở logger với mức ở handler:** sự kiện có thể bị lọc trước khi tới đích.
- **Bỏ qua interruption khi bắt exception:** có thể phá cơ chế dừng/hủy của thread; giữ tín hiệu `interrupt` khi cần.
- **Đưa dữ liệu nhạy cảm vào exception message:** stack trace và message có thể được vận chuyển đến nhiều nơi; cần hạn chế và che dữ liệu.
- **Cho rằng mức `ERROR` đồng nghĩa rollback hoặc trả HTTP 500:** logging không điều khiển transaction hay giao thức phản hồi.
- **Dựa vào số bản ghi ERROR để đếm giao dịch thất bại:** retry, trùng log, sampling và lỗi thu thập làm số liệu có thể lệch; cần xác định event kết quả chuẩn và đối chiếu nguồn trạng thái.

## 18. Tự kiểm tra kiến thức

1. **`FileNotFoundException` có nhất thiết `ERROR` không?** Không. Thiếu file tùy chọn đã có mặc định khác thiếu file bắt buộc làm dịch vụ dừng.
2. **Tại sao một input sai có thể không cần stack trace?** Vì đó là kết quả đã dự kiến và xử lý theo quy tắc; stack không giúp tìm lỗi hệ thống trong trường hợp bình thường.
3. **JUL dùng mức nào thường tương ứng với lỗi nghiêm trọng?** `Level.SEVERE`, không phải `Level.ERROR`.
4. **Làm sao ghi `IOException e` ở mức `WARNING` kèm đối tượng exception trong JUL?** `LOG.log(Level.WARNING, "event=retry_scheduled", e);`.
5. **Nếu `Logger.log(Level.SEVERE, ..., e)` chạy, Java có tự ném lại exception không?** Không. Phương thức log không điều khiển luồng ngoại lệ.
6. **Một exception bị log ở client, service và controller có thể gây vấn đề gì?** Trùng stack trace, đếm nhầm sự cố, tăng lưu lượng và khó điều tra.
7. **Người dùng hủy tác vụ, làm thread bị interrupt. Có nhất thiết là lỗi nghiêm trọng không?** Không. Cần xử lý interruption và mức log theo chính sách hủy/dừng.
8. **Một bản ghi mức `FINE` không thấy trên console mặc dù code đã gọi. Vì sao?** Có thể bị lọc ở logger, handler hoặc lớp khác trong pipeline.
9. **Một service trả 200 nhờ fallback nhưng cache bị lỗi. Có thể cần `WARNING` không?** Có, nếu suy giảm đáng theo dõi; HTTP 200 không quyết định toàn bộ mức log.
10. **Khi nào truyền `Throwable` là cần thiết?** Khi cần stack trace/cause để điều tra lỗi; nhất là thất bại ngoài dự kiến tại ranh giới ghi nhận có trách nhiệm.
11. **`getMessage()` có luôn an toàn để ghi nguyên văn không?** Không; nó có thể chứa dữ liệu nhạy cảm, đầu vào hoặc ký tự gây nhiễu định dạng log.
12. **Hai lần retry lỗi rồi lần thứ ba thành công nên có ba bản ghi `SEVERE` không?** Thường không. Hãy theo dõi lần thử riêng và kết quả cuối, tránh cảnh báo lỗi cuối khi công việc đã phục hồi.

**Điểm cần nhớ:** exception trả lời câu hỏi **“tình huống gì đã làm gián đoạn xử lý?”**, còn log level trả lời **“sự kiện này đáng chú ý đến mức nào đối với vận hành?”**. Trong Java, hãy đặt mức dựa trên tác động và phục hồi, truyền `Throwable` để giữ chẩn đoán khi cần, ghi một lần ở ranh giới phù hợp và giữ kết quả nghiệp vụ đúng độc lập với việc log có được hiển thị hay không.
