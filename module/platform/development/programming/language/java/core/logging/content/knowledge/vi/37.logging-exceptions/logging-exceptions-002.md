# Log ở service trong Java: exception, trách nhiệm và ngữ cảnh nghiệp vụ

## 1. Mục tiêu bài học

Trong một ứng dụng Java nhiều tầng, **service layer** là nơi thực thi quy tắc nghiệp vụ, phối hợp repository, gọi dịch vụ ngoài, kiểm tra trạng thái và quyết định kết quả xử lý. Vì vậy service thường có ngữ cảnh rất hữu ích để ghi log: **đơn hàng nào đang xử lý, vì sao bị từ chối, lần retry thứ mấy, dependency nào đang lỗi, trạng thái đã đổi hay chưa**.

Tuy nhiên, ghi log ở service không có nghĩa là **mọi phương thức service đều phải log** hay **mọi exception đều phải được log ngay nơi phát sinh**. Ghi sai điểm có thể làm một lỗi tạo ba, bốn stack trace giống nhau; ghi quá sớm có thể tuyên bố nghiệp vụ thành công dù transaction rollback; ghi dữ liệu thô có thể lộ PII hoặc credentials.

Mục tiêu sau bài này:

1. Xác định **khi nào service nên ghi log** và khi nào chỉ nên trả về kết quả hoặc ném exception.
2. Phân biệt **business event**, **diagnostic event**, **technical failure** và **terminal error ở boundary**.
3. Tránh anti-pattern **log-and-throw** làm trùng exception khi nhiều tầng đều ghi cùng một lỗi.
4. Dùng đúng INFO/WARN/ERROR/DEBUG, logger theo class, message template, exception cause, error code và correlation ID.
5. Hiểu sự khác nhau giữa **service quyết định thành công** và **database transaction thực sự commit**.
6. Viết, biên dịch, chạy ví dụ **Java 17 thuần JUL** với ba kịch bản: thành công, bị từ chối theo nghiệp vụ, dependency lỗi.
7. Biết áp dụng ý tưởng vào **Spring @Service, @Transactional, @RestControllerAdvice, scheduled jobs, message consumers và async tasks**.
8. Thiết kế test kiểm tra **số log event, mức log, nội dung, bảo mật và tính nhất quán khi propagate exception**.

## 2. Service layer là đâu trong luồng xử lý?

Một ứng dụng web Java thường có nhiều tầng:

~~~text
HTTP client
    │
    ▼
Servlet filter / Spring Security / Controller
    │
    ▼
OrderService (business logic)
    │
    ├── OrderRepository / database
    ├── InventoryClient / remote API
    ├── PaymentService
    └── Message publisher / outbox
    │
    ▼
Kết quả hoặc exception trả về controller
    │
    ▼
Exception handler / HTTP response
    │
    ▼
Access log / trace / metrics
~~~

Ở service, người viết code có nhiều thông tin **nghiệp vụ** mà tầng HTTP có thể không biết. Ví dụ:

- OrderService biết đơn hàng bị từ chối vì đã hết tồn kho.
- PaymentService biết lần retry thứ ba không thành công.
- AccountService biết một thao tác bị chặn vì chuyển trạng thái không hợp lệ.
- InventoryService biết bản ghi đang bị optimistic locking conflict.
- ImportService biết đã bỏ qua 12 dòng dữ liệu sai cấu trúc, tiếp tục xử lý 988 dòng còn lại.

Nhưng tầng service **không nhất thiết biết response HTTP cuối cùng**. Một exception nghiệp vụ có thể được controller mapping thành 400, 404, 409 hoặc 422; một background job không có HTTP response; gateway có thể gửi status khác. Vì vậy service nên log **ý nghĩa nghiệp vụ và nguyên nhân kỹ thuật mà nó chịu trách nhiệm**, không tự dự đoán status cuối chỉ để ghi log.

### 2.1. Hai câu hỏi phân định trách nhiệm

Trước khi thêm một lời gọi logger trong service, hãy hỏi:

- **Service đã đưa ra quyết định hoặc thực hiện hành động có ý nghĩa riêng đáng quan sát chưa?**
- **Nếu có lỗi, tầng này có xử lý lỗi, retry, fallback hoặc kết thúc trách nhiệm của mình chưa?**

Nếu câu trả lời đều **không**, việc ghi cùng stack trace rồi ném tiếp thường là dư thừa.

## 3. Phân biệt bốn loại thông tin thường ghi ở service

| Loại sự kiện | Ví dụ | Log phù hợp | Lưu ý |
| --- | --- | --- | --- |
| **Business state transition** | Đơn được chấp nhận, chuyển từ PENDING sang RESERVED. | INFO event có tên ổn định và định danh đã được phép ghi. | Không tuyên bố **đã commit** nếu transaction chưa commit. |
| **Business rejection** | Hết hàng, trạng thái không cho phép, version conflict. | INFO hoặc WARN theo policy, có **reason code**. | Có thể là kết quả dự kiến, không mặc định ERROR. |
| **Handled technical problem** | Retry sau lỗi mạng; chuyển sang fallback. | WARN, đôi khi DEBUG cho từng attempt; event cuối cần phản ánh kết quả. | Nếu đã xử lý xong, có thể cần log tại service vì không còn exception lên trên. |
| **Unhandled technical failure** | Dependency down, database exception, bug bất ngờ. | Thường ném exception giữ cause; log stack trace tại **boundary sở hữu kết quả cuối**. | Tránh service log ERROR cùng exception rồi controller cũng log ERROR. |

Mục tiêu là người vận hành đọc log và nhận biết **một sự kiện nghiệp vụ độc lập** khác với **một lỗi chưa được xử lý**.

Ví dụ, hai record sau có ý nghĩa khác nhau:

~~~text
INFO  event=order.rejected orderId=O-204 reason=OUT_OF_STOCK
ERROR event=request.failed errorCode=INVENTORY_UNAVAILABLE cause=ConnectException
~~~

Record đầu là **quyết định nghiệp vụ** có thể được API trả 409. Record sau là **lỗi kỹ thuật chưa xử lý được tại boundary**, có thể được API trả 503. Không có quy tắc rằng mọi HTTP 409 phải log ERROR.

## 4. Nguyên tắc nền tảng: log đúng một lần cho một failure chain

Một anti-pattern kinh điển:

~~~java
// Minh họa sai: trong repository.
catch (SQLException ex) {
    log.error("Cannot query order", ex);
    throw ex;
}
~~~

~~~java
// Minh họa sai: trong service.
catch (Exception ex) {
    log.error("Cannot place order", ex);
    throw ex;
}
~~~

~~~java
// Minh họa sai: trong controller.
catch (Exception ex) {
    log.error("Request failed", ex);
    throw ex;
}
~~~

Một exception duy nhất đã bị ghi **ba lần**, với ba stack trace. Trong hệ thống có nhiều tầng và retry, số bản ghi còn tăng hơn. Điều này:

- Làm dashboard đếm lỗi nhiều hơn số request lỗi thực.
- Tăng chi phí ingest/storage và độ nhiễu.
- Khiến người điều tra tưởng có ba lỗi độc lập.
- Có thể rò rỉ cùng dữ liệu nhạy cảm ở nhiều đích.
- Che khuất nơi failure cuối cùng được chuyển thành response hoặc retry/fallback.

**Quy tắc thực hành:** nếu service **không xử lý lỗi và chỉ chuyển tiếp**, hãy giữ nguyên cause/context rồi **để boundary quyết định log terminal failure một lần**. Service vẫn có thể phát **business/diagnostic event riêng** nếu event đó mang ý nghĩa độc lập, không phải bản sao stack trace.

~~~text
Repository ném lỗi
       │
       ▼
Service thêm exception context (nếu cần), không log stack
       │
       ▼
Boundary quyết định kết quả cuối
       │
       └── ERROR + exception cause + request context (một lần)
~~~

### 4.1. Đây là guideline, không phải luật cấm log ở mọi tầng

Nếu service **nuốt exception hợp lệ, thực hiện fallback hoặc retry rồi trả về bình thường**, boundary sẽ **không thấy lỗi ban đầu**. Khi đó service có trách nhiệm ghi lại việc đã xử lý, nếu sự kiện đáng quan sát:

~~~text
WARN event=inventory.lookup.fallback dependency=inventory reason=TIMEOUT
INFO event=order.created source=CACHED_INVENTORY
~~~

Tương tự, khi một background worker là **boundary cuối** của message/job, worker/service có thể phải ghi lỗi terminal vì không có controller ghi thay.

Một nguyên tắc hữu ích là **mỗi failure chain có một nơi sở hữu terminal error log**, còn các tầng khác chỉ ghi **sự kiện độc lập** hoặc **trạng thái retry/fallback có ý nghĩa**.

## 5. Khi nào service nên log?

### 5.1. Thay đổi trạng thái nghiệp vụ quan trọng

Ví dụ đơn hàng đang ở PENDING và được service chuyển sang RESERVED. Một event có cấu trúc giúp phân tích và hỗ trợ truy vết:

~~~text
INFO event=order.reservation.requested orderId=O-101 from=PENDING to=RESERVED
~~~

Nhưng nếu method đang nằm trong transaction chưa commit, chữ **requested** hoặc **attempted** chính xác hơn **committed**. Cần xem phần transaction bên dưới để tránh thông báo thành công giả.

Không nhất thiết ghi một event ở mọi phương thức getter hoặc setter. Chọn **business milestone** thực sự hữu ích và có chính sách lưu giữ.

### 5.2. Một quy tắc từ chối có ý nghĩa vận hành

~~~text
INFO event=order.rejected orderId=O-102 reason=OUT_OF_STOCK
~~~

Từ chối vì hết hàng có thể là hành vi hoàn toàn bình thường. Ghi INFO giúp phân tích tỷ lệ từ chối; nếu policy xem đây là tình trạng đáng cảnh báo thì có thể dùng WARN hoặc metric riêng. Không tự gắn ERROR cho mọi exception nghiệp vụ.

### 5.3. Retry hoặc fallback mà service thực sự điều khiển

~~~text
WARN event=inventory.retry attempt=2 maxAttempts=3 reason=TIMEOUT
WARN event=inventory.fallback mode=CACHED_STOCK reason=DEPENDENCY_UNAVAILABLE
~~~

Nếu service có ba lần retry, không nhất thiết in ba stack trace ERROR. Có thể log từng attempt ở DEBUG/WARN theo policy, sau đó chỉ ghi một terminal error nếu toàn bộ chuỗi thất bại và không có tầng khác chịu trách nhiệm.

Lưu ý: retry không nên mặc định dùng với mọi request, đặc biệt với giao dịch **không idempotent**; quyết định retry cần timeout, backoff, idempotency, circuit breaker và giới hạn số lần phù hợp. Logging không tự làm retry an toàn.

### 5.4. Phát hiện bất biến nghiệp vụ hoặc dữ liệu bất thường

Nếu gặp một trạng thái **theo thiết kế không thể xảy ra**, service có thể ghi một event phù hợp rồi fail hoặc phát tín hiệu giám sát. Tránh cả hai cực đoan: bỏ qua lỗi hoặc log stack ở mọi tầng. Một exception type và error code rõ có thể giúp boundary xử lý.

### 5.5. Batch job hoặc consumer là điểm kết thúc trách nhiệm

Một service được gọi từ scheduled job hoặc message listener có thể không đi qua HTTP exception handler. Nếu worker **quyết định bỏ qua message, đưa vào dead-letter queue hoặc đánh dấu job FAILED**, đây là một quyết định đáng ghi log ở boundary của job/consumer.

Phải phân biệt **một message được retry nhiều lần** với **nhiều message khác nhau**; gắn message ID, attempt number và outcome để tránh hiểu nhầm log trùng là sự cố mới.

## 6. Khi nào service không nên log?

- **Mọi lần method được gọi** ở INFO nếu lưu lượng cao mà không có ý nghĩa vận hành: tăng khối lượng và chi phí.
- **Mọi exception vừa catch vừa throw lại**, khi boundary đã log terminal failure.
- **Mọi request/response body** vì tiện gỡ lỗi; có thể chứa PII, token, thông tin thanh toán.
- **Thông báo “success” trước commit** rồi bỏ qua khả năng transaction rollback.
- **Thông tin có thể suy ra từ access log** mà không thêm context nghiệp vụ.
- **Đoạn code đang thử nghiệm** với System.out.println/System.err.println trong production thay vì backend cấu hình được.
- **Các giá trị đầu vào không được escape/validate** rồi ghép trực tiếp thành text log, gây log injection.
- **Toàn bộ exception.getMessage() từ bên ngoài** nếu message chứa URL, header, SQL parameter hoặc dữ liệu cá nhân.
- **Mức ERROR cho lỗi nghiệp vụ đã dự kiến**, làm tăng báo động giả.
- **Quá nhiều event lặp dưới retry**, khiến dashboard dễ đếm một sự cố nhiều lần.

Một câu hỏi chốt: **khi vận hành thực tế, ai sẽ dùng dòng log này để ra quyết định gì?** Nếu không có câu trả lời, cân nhắc giảm severity, dùng metric hoặc bỏ event.

## 7. Ví dụ Java 17 độc lập: service log sự kiện, boundary log exception

Mô hình này dùng **java.util.logging (JUL)** có sẵn trong JDK 17 để minh họa phân chia trách nhiệm. Không cần Spring Boot, Maven hay thư viện ngoài.

Ba kịch bản:

1. **O-100 / OK:** service hoàn tất bước xử lý của mô phỏng và ghi một business event INFO; entry point trả kết quả.
2. **O-200 / OUT_OF_STOCK:** service quyết định từ chối, ghi event INFO có reason code và ném exception nghiệp vụ; entry point chuyển kết quả thành một mã phản hồi mô phỏng **409**, **không log lại cùng failure**.
3. **O-300 / INVENTORY_DOWN:** service gặp lỗi dependency, giữ exception và ném lên; entry point là **terminal boundary**, ghi một ERROR/SEVERE kèm cause, rồi tạo mã phản hồi mô phỏng **503**.

Đây **không phải web server thật** và các dòng "HTTP" chỉ là **kết quả mô phỏng tại boundary**. Mục tiêu là quan sát số event và nơi log, không kiểm thử HTTP network.

### 7.1. Mã nguồn hoàn chỉnh

Lưu **ServiceLoggingDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ServiceLoggingDemo {

    enum Scenario {
        OK, OUT_OF_STOCK, INVENTORY_DOWN
    }

    static final class OutOfStockException extends RuntimeException {
    }

    static final class InventoryUnavailableException
            extends RuntimeException {
    }

    record Receipt(String orderId) {
    }

    static final class OrderService {
        private static final Logger LOG =
                Logger.getLogger("demo.orders.OrderService");

        Receipt create(String orderId, Scenario scenario) {
            if (scenario == Scenario.OUT_OF_STOCK) {
                LOG.info("order.rejected orderId=" + orderId
                        + " reason=OUT_OF_STOCK");
                throw new OutOfStockException();
            }

            if (scenario == Scenario.INVENTORY_DOWN) {
                // Khong log stack trace roi nem lai o service.
                throw new InventoryUnavailableException();
            }

            LOG.info("order.accepted orderId=" + orderId);
            return new Receipt(orderId);
        }
    }

    static final class EntryPoint {
        private static final Logger LOG =
                Logger.getLogger("demo.orders.EntryPoint");
        private final OrderService service = new OrderService();

        void handle(String orderId, Scenario scenario) {
            try {
                Receipt receipt = service.create(orderId, scenario);
                System.out.println(
                        "HTTP 201 orderId=" + receipt.orderId());
            } catch (OutOfStockException ex) {
                // Business rejection da duoc service ghi event.
                // Khong can log lai cung mot exception.
                System.out.println("HTTP 409 code=OUT_OF_STOCK");
            } catch (InventoryUnavailableException ex) {
                // Boundary so huu log terminal error mot lan.
                LOG.log(Level.SEVERE,
                        "request.failed orderId=" + orderId, ex);
                System.out.println(
                        "HTTP 503 code=INVENTORY_UNAVAILABLE");
            }
        }
    }

    private static Handler stdoutHandler() {
        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(getFormatter().format(record));
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String cause = record.getThrown() == null
                        ? ""
                        : " cause="
                                + record.getThrown()
                                        .getClass().getSimpleName();

                return record.getLevel().getName() + " "
                        + record.getLoggerName() + " "
                        + record.getMessage() + cause;
            }
        });
        return handler;
    }

    public static void main(String[] args) {
        Logger packageLogger = Logger.getLogger("demo.orders");
        packageLogger.setLevel(Level.ALL);
        packageLogger.setUseParentHandlers(false);
        Handler handler = stdoutHandler();
        packageLogger.addHandler(handler);

        try {
            EntryPoint entry = new EntryPoint();
            entry.handle("O-100", Scenario.OK);
            entry.handle("O-200", Scenario.OUT_OF_STOCK);
            entry.handle("O-300", Scenario.INVENTORY_DOWN);
        } finally {
            packageLogger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

### 7.2. Biên dịch và chạy

~~~bash
javac ServiceLoggingDemo.java
java ServiceLoggingDemo
~~~

**stdout dự kiến với JDK 17 trở lên:**

~~~text
INFO demo.orders.OrderService order.accepted orderId=O-100
HTTP 201 orderId=O-100
INFO demo.orders.OrderService order.rejected orderId=O-200 reason=OUT_OF_STOCK
HTTP 409 code=OUT_OF_STOCK
SEVERE demo.orders.EntryPoint request.failed orderId=O-300 cause=InventoryUnavailableException
HTTP 503 code=INVENTORY_UNAVAILABLE
~~~

Tại sao output có thể dự đoán:

- Chương trình chạy tuần tự một thread, không dùng thời gian hay random.
- Logger con **demo.orders.OrderService** và **demo.orders.EntryPoint** kế thừa cấu hình từ logger **demo.orders**; parent này giữ handler duy nhất và **setUseParentHandlers(false)** để không in bản sao qua JUL root handler.
- Formatter cố ý chỉ in **level, logger name, message và loại exception** để kết quả không phụ thuộc timestamp hay stack trace line numbers.
- Scenario OUT_OF_STOCK tạo **một business event ở service**, entry point không ghi exception lần hai.
- Scenario INVENTORY_DOWN không tạo business event thành công; **boundary ghi một terminal failure** và giữ được đối tượng Throwable trong LogRecord.
- Dòng "HTTP 201/409/503" chỉ là mô phỏng mapping kết quả ứng dụng, không có socket hay servlet.

### 7.3. Giới hạn của ví dụ

Trong production, **đừng dùng handler tối giản của demo**. Formatter ở đây chỉ in **tên loại exception**, cố ý không in stack trace để bài có stdout ổn định. Backend thực tế nên hỗ trợ **Throwable + stack trace** tại điểm log terminal failure, cùng chính sách redaction/structured fields và bộ đệm phù hợp.

Mã demo dùng orderId tĩnh đã biết; nếu orderId đến từ client, hãy **validate và encode theo định dạng log**, tránh CRLF/log forging hoặc dữ liệu nhạy cảm. Kết quả 201 cũng **không chứng minh transaction database đã commit** vì chương trình không có transaction.

Thử đổi phần catch OUT_OF_STOCK thành:

~~~java
// Anti-pattern: ghi cùng exception rồi tiếp tục đã xử lý.
LOG.log(Level.SEVERE, "Order failed", ex);
System.out.println("HTTP 409 code=OUT_OF_STOCK");
~~~

Nếu thêm log như vậy, cùng một business rejection vừa có INFO "order.rejected" vừa có SEVERE stack trace, làm thống kê severity gây nhiễu. Hãy quyết định **sự kiện nào cần log, ở cấp nào**, thay vì tự động log exception bất cứ khi nào catch.

## 8. Log exception đúng cách trong service

### 8.1. Đừng bỏ cause khi wrap exception

Nếu service cần **dịch exception hạ tầng thành exception nghiệp vụ/kỹ thuật rõ nghĩa**, giữ nguyên cause:

~~~java
// Đoạn minh họa; cần các lớp trong dự án thực.
try {
    inventoryClient.reserve(orderId);
} catch (RemoteInventoryException ex) {
    throw new InventoryUnavailableException(
            "Inventory service unavailable", ex);
}
~~~

Đoạn trên giả định InventoryUnavailableException có constructor (String, Throwable) phù hợp trong dự án. **Không phải đoạn code độc lập** và không sử dụng cùng class ngoại lệ rỗng của phần 7.

Một mẫu không tốt:

~~~java
// BAD: mat original cause.
catch (RemoteInventoryException ex) {
    throw new RuntimeException("Cannot reserve inventory");
}
~~~

Khi mất cause, boundary sẽ khó phân biệt timeout, network reset, permission denied hay bug. **Service có thể thêm thông tin nghiệp vụ qua exception type/code mà không cần log lỗi ngay**.

### 8.2. Giữ thông điệp lỗi an toàn

Thông điệp exception có thể chứa dữ liệu từ external API, SQL, path, URL, HTTP headers hoặc input người dùng. Khi wrap, dùng error code ổn định; đừng nhúng token, password, body hoặc toàn bộ exception text vào message mới một cách vô kiểm soát.

Cần phân biệt:

- **Thông tin nội bộ cho kỹ thuật:** exception type, cause chain, stack trace, service/dependency, traceId.
- **Thông tin trả cho client:** error code/mô tả đã được duyệt, không lộ internal stack/credential.
- **Thông tin trong log:** chỉ các field cần điều tra và được phép lưu theo policy.

### 8.3. SLF4J: truyền Throwable cho backend

Trong dự án đã có SLF4J 2.x và provider tương thích, một cách ghi terminal exception rõ ràng:

~~~java
// Đoạn minh họa; cần biến logger, orderId và Throwable ex.
logger.atError()
      .addKeyValue("event", "order.request.failed")
      .addKeyValue("orderId", orderId)
      .addKeyValue("errorCode", "INVENTORY_UNAVAILABLE")
      .setCause(ex)
      .log("Order request failed");
~~~

API fluent của SLF4J 2.x hỗ trợ đặt cause cho event; nhưng **backend/layout quyết định cách in Throwable và key-value pairs**. Nếu encoder không đưa các key-value pairs vào output, có thể không thấy chúng trên dashboard. Kiểm tra cấu hình thật.

Với SLF4J kiểu thông thường:

~~~java
// Minh họa: ghi exception object, không chỉ message của nó.
logger.error("Order request failed, orderId={}", orderId, ex);
~~~

Ở phiên bản SLF4J phổ biến, Throwable ở tham số cuối được backend nhận làm cause. Tránh biến nó thành chuỗi:

~~~java
// BAD: chi ghi chuoi message, bo mat stack/cause.
logger.error("Order request failed: {}", ex.getMessage());
~~~

Tuy nhiên, **giữ cause không đồng nghĩa log mọi tầng**. Chỉ chọn nơi chịu trách nhiệm terminal failure.

### 8.4. JUL: log với tham số Throwable

JUL có overload:

~~~java
// Minh họa, không phải main độc lập.
logger.log(
        java.util.logging.Level.SEVERE,
        "Inventory operation failed",
        exception);
~~~

Đoạn này tạo LogRecord có Throwable; formatter/handler quyết định cách xuất stack. Nếu chỉ làm:

~~~java
// BAD: exception.toString() khong tu ghi day du stack trace.
logger.severe("Inventory operation failed " + exception);
~~~

thì thường chỉ có loại exception và message mà không có stack trace chi tiết. Cùng nguyên tắc được áp dụng với backend Java khác.

## 9. Service exception và mapping ở HTTP boundary

Một kiến trúc Spring Boot thường phân chia:

~~~text
OrderController
    │
    ▼
OrderService
    │
    ├── success → trả kết quả
    ├── business conflict → throw OutOfStockException
    └── infrastructure failure → throw InventoryUnavailableException
    │
    ▼
@RestControllerAdvice / framework exception resolver
    │
    ├── 201 hoặc 200 (từ controller)
    ├── 409 (business conflict)
    └── 503 (dependency unavailable)
    │
    ▼
Access log ghi HTTP status; error log terminal tại điểm phù hợp
~~~

**Các HTTP code chỉ là ví dụ hợp đồng API.** Một hệ thống khác có thể dùng 422 cho vi phạm quy tắc nghiệp vụ, 404 khi tài nguyên không tồn tại hoặc 500 khi không xác định. **Không tự suy ra mã HTTP từ tên exception Java**.

### 9.1. Phân biệt @Service và @RestControllerAdvice

Trong Spring, một method thuộc @Service thường được nhiều loại caller sử dụng: HTTP controller, scheduled job, Kafka consumer, batch task. Vì vậy service nên có contract exception và business event **không phụ thuộc HTTP**.

Một exception handler ở web boundary có thể ghi terminal failure khi cần:

~~~java
// Minh họa trong ứng dụng Spring Web đã có imports, types và logger.
@ExceptionHandler(InventoryUnavailableException.class)
public ResponseEntity<ApiError> inventoryFailure(
        InventoryUnavailableException ex) {
    logger.error("HTTP request failed: inventory unavailable", ex);

    ApiError body = new ApiError("INVENTORY_UNAVAILABLE");
    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(body);
}
~~~

Đoạn trên **không phải chương trình độc lập**: phải có @RestControllerAdvice, ApiError, lớp exception, logger và dependency Spring. Nếu một centralized exception handler khác đã log Throwable, đừng log lặp thêm trong handler này.

Một business conflict như OutOfStockException có thể chỉ cần trả 409 và dựa trên business event INFO ở service. Nếu access log đã ghi response status=409, không bắt buộc thêm ERROR.

### 9.2. Có nên log exception ở controller lẫn advice?

Thông thường **không**, nếu cả hai đều ghi cùng stack. Chọn **một owner cho terminal error** tại web boundary. Các layer còn lại truyền/chuẩn hóa exception theo contract.

Cần nhớ **@RestControllerAdvice không bắt hết mọi nguồn lỗi**: security filter có thể từ chối trước controller, servlet container có error dispatch riêng, và async/background job có boundary khác. Chính sách log phải bao phủ các kiểu entry point thực sự.

## 10. Transaction: đừng ghi "đã thành công" quá sớm

Đây là một lỗi quan trọng khi log ở service.

### 10.1. Vì sao ghi log trong @Transactional có thể sai?

Giả sử code Spring:

~~~java
// Minh họa trong service dùng Spring Transaction Management.
@Transactional
public OrderReceipt createOrder(CreateOrderCommand command) {
    Order saved = repository.save(buildOrder(command));
    logger.info("order.created orderId={}", saved.getId());
    return toReceipt(saved);
}
~~~

Ngay sau logger.info, transaction **có thể chưa commit**. Với Spring transaction proxy tiêu chuẩn, commit thường được thực hiện khi method hoàn tất và advice xử lý transaction; transaction vẫn có thể rollback vì lỗi ở thao tác flush/commit, hoặc vì caller có outer transaction tiếp tục xử lý rồi rollback.

Dòng log "order.created" dễ bị diễn giải là **đã lưu bền vững**, trong khi database cuối cùng **không commit**. Log không tự rollback cùng transaction.

### 10.2. Cách diễn đạt stage đúng

Nếu ghi trong transaction, nên đặt event name phản ánh **ý định hoặc mốc xử lý thực**:

~~~text
INFO event=order.create.attempted orderId=O-350
INFO event=order.validation.passed orderId=O-350
~~~

Không dùng từ **committed** nếu chưa có bằng chứng commit. Cần cân nhắc có cần cả hai event không; thường không nên ghi mọi bước nhỏ ở INFO.

### 10.3. Ghi sự kiện sau commit

Với Spring, có thể thiết kế domain event và subscriber xử lý sau commit qua **@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)**. Ví dụ mô tả luồng:

~~~text
@Service @Transactional
    │
    ├── Lưu Order
    ├── Phát domain event trong transaction
    └── Method return
            │
            ▼
      Transaction commit
            │
            ▼
  Listener AFTER_COMMIT → ghi event "committed"
~~~

Đây là **một lựa chọn kiến trúc** chứ không phải bảo đảm giao nhận tuyệt đối. Listener chạy sau commit **vẫn có thể không ghi được log** nếu process crash hoặc sink lỗi. Khi cần chắc chắn sự kiện nghiệp vụ downstream không thất lạc, dùng cơ chế bền vững như **transactional outbox**, idempotent consumer và retry có kiểm soát.

Ngoài ra, một listener AFTER_COMMIT **không tự chạy khi không có transaction** nếu cấu hình mặc định không cho fallback; phải hiểu phiên bản và lifecycle của framework.

### 10.4. Giao dịch lồng nhau và retry

Một service method hoàn tất không đồng nghĩa toàn bộ workflow đã hoàn tất. Outer transaction có thể rollback, message consumer có thể retry hoặc payment gateway có thể chấp nhận yêu cầu nhưng callback hoàn thành sau. Đặt event name phản ánh **thực tế nghiệp vụ tại thời điểm log**, không phóng đại trạng thái.

## 11. Chọn level cho log ở service

| Tình huống service | Level thường phù hợp | Lý do |
| --- | --- | --- |
| Business milestone đã định nghĩa rõ | INFO | Có giá trị vận hành, nên quản lý volume. |
| Kết quả bị từ chối theo rule bình thường | INFO hoặc WARN | Không phải bug; dùng reason code và metrics. |
| Debug một nhánh quyết định nội bộ | DEBUG | Chi tiết chỉ cần khi chẩn đoán. |
| Dấu vết rất chi tiết | TRACE | Khối lượng lớn; không bật rộng ở production. |
| Một retry tạm thời vẫn trong giới hạn | DEBUG/WARN tùy ý nghĩa | Tránh stack trace ERROR mỗi attempt. |
| Retry exhausted nhưng exception được propagate | Không bắt buộc log ở service | Boundary cuối có thể log ERROR một lần. |
| Fallback thành công nhưng giảm chất lượng dịch vụ | WARN | Service đã xử lý sự cố; boundary có thể trả thành công. |
| Invariant quan trọng bị phá vỡ | ERROR nếu service sở hữu terminal failure; khác đi thì propagate | Điều tra cause ở điểm có đủ context. |
| Dependency down chưa được xử lý | Propagate Throwable hoặc wrap có cause | Không mặc định log stack ở service và tầng trên. |
| Sự kiện audit có nghĩa vụ lưu giữ | Dùng audit/event pipeline theo chính sách | Logging thông thường không bảo đảm durability và integrity. |

**Không tồn tại mapping tự động**: exception checked = WARN, unchecked = ERROR. Loại exception là cơ chế Java; mức log phản ánh **mức độ sự kiện và trách nhiệm xử lý**.

Tương tự, nếu một service trả Optional.empty theo contract, đó không phải exception và không tự động là lỗi. Có thể không cần log gì hoặc ghi một event nghiệp vụ nếu có ý nghĩa.

## 12. Log context: correlation ID, mã lỗi và logger name

Một record service hữu ích nên chứa **định danh ổn định** để liên kết với request/tracing:

~~~json
{
  "event": "order.reservation.failed",
  "service": "order-service",
  "environment": "prod",
  "logger": "com.example.orders.OrderService",
  "order_id": "O-401",
  "error_code": "INVENTORY_UNAVAILABLE",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "attempt": 3
}
~~~

Đây là **JSON minh họa**, không phải output mặc định của SLF4J, JUL hay Spring Boot. **trace_id** phải đến từ tracing context hợp lệ; không tự gán giá trị giả trong production. Có thể dùng span ID, request ID hoặc message ID tùy entry point và hạ tầng.

### 12.1. Logger name theo class

Thực hành thông dụng với SLF4J:

~~~java
// Minh họa trong một class OrderService có SLF4J dependency.
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);
~~~

Quy ước logger theo class giúp tìm log theo package hoặc service. Nếu dùng logger đặt tên tùy ý, phải đảm bảo naming convention và không trộn nhiều category gây khó cấu hình mức log.

### 12.2. Stable event name và error code

Thay vì chỉ ghi câu văn tự do:

~~~text
Failed unexpectedly!
~~~

hãy giữ event và error code ổn định để dashboard/query không phụ thuộc câu chữ:

~~~text
event=inventory.reserve.failed errorCode=REMOTE_TIMEOUT orderId=O-401
~~~

Message cho con người vẫn hữu ích, nhưng event name/error code ổn định giúp aggregation và cảnh báo. Không dùng raw exception message làm error code, vì nội dung đó có thể thay đổi theo vendor/version hoặc chứa dữ liệu không tin cậy.

### 12.3. MDC và ThreadLocal context

Với SLF4J/Logback hoặc Log4j2, MDC/ThreadContext hỗ trợ gắn context như traceId/requestId vào log. Nó thường gắn với **thread hoặc execution context**, không tự động truyền qua mọi ExecutorService, @Async, CompletableFuture, Reactor hoặc message consumer.

Ví dụ minh họa trong ứng dụng dùng SLF4J:

~~~java
// Minh họa: requestId đã được validate ở boundary.
try {
    MDC.put("requestId", requestId);
    orderService.createOrder(command);
} finally {
    MDC.remove("requestId");
}
~~~

Trong hệ thống có nhiều giá trị MDC, dùng cơ chế **capture/restore** phù hợp backend và framework; không vô tình xóa context mà caller sở hữu. Nếu luồng xử lý chuyển thread, cần instrumentation/context propagation đã được kiểm chứng. **Không đặt password/token vào MDC** chỉ để tiện tìm log.

### 12.4. Vì sao context không được quyết định quyền?

Một trace ID hoặc tenant ID do client gửi có thể bị giả mạo. Validate theo grammar, phân biệt tenant đã xác thực với tenant header, và encode theo output format. **Không dùng nội dung MDC do client kiểm soát để cấp quyền đọc log hoặc định tuyến secrets**.

## 13. Service gọi remote API: logging request và failure

Khi service gọi HTTP client, database hoặc broker, cần tách:

- **Outcome của dependency attempt**: timeout, connection refused, 429, 503, parse failure.
- **Outcome của service operation**: retry thành công, fallback, ném exception.
- **Outcome của entry point**: HTTP 201/409/503, job success/failure, message ACK/NACK.

Một attempt nhận 503 không có nghĩa toàn bộ request business trả 503, vì service có thể retry thành công. Nếu ghi ERROR cho attempt đầu rồi operation cuối thành công, dashboard có thể báo đỏ dù giao dịch thực không thất bại.

Mẫu hợp lý:

~~~text
DEBUG event=inventory.call.retry attempt=1 reason=HTTP_503
WARN  event=inventory.call.retry attempt=2 reason=HTTP_503
INFO  event=order.created inventorySource=LIVE
~~~

Hoặc khi retry exhausted:

~~~text
WARN  event=inventory.call.retry_exhausted attempts=3
ERROR event=http.request.failed errorCode=INVENTORY_UNAVAILABLE
~~~

Hai record ở trường hợp sau chỉ hợp lý khi **retry_exhausted là event vận hành độc lập**; không ghi trùng stack cause ở cả hai dòng. Một implementation cũng có thể chỉ ghi terminal ERROR nếu metric đã đo retry; đừng bắt buộc mọi sự kiện phải có log.

### 13.1. Không log toàn bộ request/response body

Remote response có thể chứa token, customer data, session cookie, card data hoặc thông tin nội bộ. Khi cần chẩn đoán, ưu tiên **host/service đã được phép ghi, operation, status, elapsed time, attempt, error type và correlation ID**. Có thể redact query parameters. Kích thước response lớn cũng là nguyên nhân log flooding.

### 13.2. Đo duration cho service call

Trong Java, **System.nanoTime()** phù hợp để đo **thời lượng tương đối**, không dùng để tạo timestamp toàn cục:

~~~java
// Đoạn minh họa, không phải class Java độc lập.
long start = System.nanoTime();
try {
    return inventoryClient.reserve(orderId);
} finally {
    long elapsedNanos = System.nanoTime() - start;
    metrics.recordInventoryLatency(elapsedNanos);
}
~~~

Log latency ở những mốc cần thiết; đo bằng metric thường hiệu quả hơn ghi INFO cho mỗi method call. Nếu dùng tracing/metrics, không cần lặp quá nhiều field khi đã có correlation.

## 14. Phòng ngừa lộ dữ liệu từ log service

Service nắm nhiều dữ liệu nghiệp vụ nên có nguy cơ vô tình ghi dữ liệu nhạy cảm cao hơn tầng truy cập.

**Không nên log**:

- Password, OTP, API key, access token, refresh token, Authorization/Cookie headers.
- Dữ liệu thanh toán chưa được phép lưu, thẻ, tài khoản nhạy cảm, raw webhook secrets.
- Toàn bộ DTO của request/response nếu DTO có PII hoặc field không kiểm soát.
- Raw SQL parameters, connection strings có password, internal credentials.
- Exception message từ remote service nếu chứa data không đáng tin.
- Nội dung message queue lớn hoặc user-generated text chưa escape.

Một nguyên tắc quan trọng là **log tối thiểu những gì cần thiết để điều tra**, thay vì log "toString() của toàn bộ object" theo thói quen.

### 14.1. Redaction không thay thế phân quyền

Nếu user ID cần thiết cho hỗ trợ, cân nhắc pseudonymization/masking theo policy; nhưng mã ẩn danh vẫn có thể liên kết hành vi nhiều lần. Log storage cần quyền đọc, retention và audit tương ứng. Không tự cho rằng môi trường dev/CI không chứa dữ liệu thật.

### 14.2. Input và log injection

Một orderId hoặc user-provided reason có thể chứa CR/LF, dấu phân cách hay ký tự điều khiển. Dùng **structured JSON encoder** hoặc cơ chế escape theo đúng format sink, validate các field ID và tránh tự xây JSON bằng nối chuỗi. Message template cố định của SLF4J là tốt, nhưng **không tự bảo đảm** CRLF không bị chuyển thành dòng giả trong plain text layout.

### 14.3. Đừng leak exception qua API response

Server log có thể giữ cause chain nếu được phép, nhưng client không nên nhận stack trace hoặc internal hostname chỉ vì service ném exception. API response dùng **error code an toàn và message ngắn**, trace/request ID hỗ trợ liên hệ.

## 15. Spring @Transactional: rollback, retry và event quan sát

### 15.1. @Transactional không tự đồng bộ log

Một record được in ra console hay gửi đến Kafka logger appender **không tự nằm trong database transaction**. Nếu transaction rollback, log đã phát **không được rollback theo**. Mọi statement "đã commit" phải gắn với mốc commit thực tế hoặc cơ chế event durable tương ứng.

### 15.2. Exception và rollback rule

Mặc định, Spring declarative transaction thường rollback với **RuntimeException/Error**, không tự rollback mọi **checked exception** trừ khi cấu hình rollback rules. Vì vậy:

- Đừng suy ra transaction rollback chỉ vì code bắt được Exception.
- Đừng catch lỗi rồi trả giá trị thành công nếu thực chất cần rollback.
- Cần hiểu rollbackFor/noRollbackFor và outer transaction.
- Nếu code intercept exception rồi swallow, có thể thay đổi transaction outcome; logging không thay thế quyết định transaction.

Khi lỗi xảy ra, service nên giữ exception semantics rõ ràng; boundary có thể map response phù hợp.

### 15.3. Retry sau transaction failure

Một transaction bị conflict có thể được retry. Nếu service log "created" ở mỗi attempt, log có thể ghi ba "created" dù cuối cùng chỉ một commit hoặc không có commit nào. Ghi **attempt** nếu cần, và chỉ ghi **committed** khi sự kiện đã thực sự commit theo hợp đồng.

### 15.4. Event nghiệp vụ quan trọng không phụ thuộc logger

Nếu một thanh toán phải phát event downstream dù process crash sau commit, hãy lưu **outbox row trong cùng database transaction** và dùng publisher có retry/idempotency. Một dòng INFO không phải event delivery guarantee; logging thường là best-effort và có thể rơi do queue/backpressure/file/collector.

## 16. Batch, scheduler và message consumer: boundary không phải controller

Cùng một OrderService có thể được gọi qua nhiều kiểu entry point:

| Entry point | Boundary sở hữu terminal outcome | Logging cần lưu ý |
| --- | --- | --- |
| HTTP controller | Exception handler/access log | HTTP status, route, traceId; không log hai stack trace. |
| Scheduled job | Job runner/scheduler | Job ID, run ID, retries, final success/failure. |
| Kafka/RabbitMQ listener | Message listener/consumer adapter | Message ID, partition/offset khi được phép, attempt, ACK/NACK/DLQ. |
| CLI command | Command handler/main | Exit code, operation, terminal exception. |
| Async task | Task runner/future completion | Exception không bị mất trong Future; context propagation. |
| Batch import | Chunk/item processor hoặc job step | Số bản ghi thành công/thất bại, không log từng dòng vô ích. |

Nếu business service luôn log ERROR rồi rethrow, caller nào cũng nhận lỗi **đã được log trước** và lại ghi thêm terminal error theo ngữ cảnh riêng. Thiết kế tốt hơn là **service ném exception có nghĩa**, còn boundary cụ thể ghi terminal failure với context của nó.

### 16.1. Exception trong CompletableFuture

Một tác vụ async có thể thất bại và được giữ trong **CompletableFuture**. Nếu không có caller nào observe completion, failure khó phát hiện. Đặt handler terminal khi kết thúc pipeline, dùng metrics/log phù hợp; không để service log stack rồi tiếp tục throw qua nhiều exceptionally/handle stages.

### 16.2. Message retry và duplicate logging

Một message có thể chạy lại sau timeout hoặc consumer restart. Nếu event có cùng messageId nhưng attempt khác nhau, phải phân biệt **retry của cùng việc** với **nhiều business event khác nhau**. Không log "processed" trước khi ACK/commit theo contract rồi tưởng message đã xử lý một lần duy nhất.

## 17. Testing: kiểm tra log ở service, không chỉ return value

Một test service tốt cần xác minh cả **kết quả/exception** và **hệ quả logging** nếu log là một phần hợp đồng quan sát.

### 17.1. Bảng tình huống

| Kịch bản | Service behavior | Log nên có | Log không nên có |
| --- | --- | --- | --- |
| Tạo đơn hợp lệ | Trả kết quả | Một business event hợp lệ (nếu policy yêu cầu). | Stack trace ERROR. |
| Hết hàng | Ném business exception hoặc trả rejection | Business reason code phù hợp. | ERROR trùng nếu boundary đã xử lý dự kiến. |
| Remote inventory timeout | Wrap/propagate cause | Terminal error ở boundary cuối. | Stack trace giống nhau ở mọi tầng. |
| Retry rồi thành công | Trả thành công cuối | Retry summary/metric và success phù hợp. | Nhiều terminal ERROR cho các attempt đã phục hồi. |
| Retry exhausted | Propagate failure cuối | Một terminal error có cause và attempts. | Event "success" giả. |
| Transaction rollback | Không commit | Attempt/rollback event nếu hữu ích. | Event "committed" trước commit. |
| Background job fail | Job đánh dấu fail | Job-level terminal event có job/run ID. | Phụ thuộc vào HTTP advice vốn không chạy. |
| Dữ liệu cá nhân trong DTO | Xử lý đúng | Field đã cho phép và redact. | Raw DTO/token/password. |
| Input chứa CRLF | Xử lý theo policy | Event giữ cấu trúc một record ở sink. | Dòng giả do log injection. |
| Async context propagation | Chuyển qua executor | Correlation ID phù hợp hoặc rõ ràng vắng mặt. | Trace ID của request trước bị rò qua ThreadLocal. |
| Log backend lỗi | Business flow theo policy | Error telemetry độc lập khi có thể. | Kết luận rằng logger luôn lưu bền vững. |

### 17.2. Cách test số lượng event

Với Logback/Log4j2 hoặc JUL, có thể gắn **test appender/handler** vào logger được kiểm soát rồi assert:

- Scenario success có đúng event name, level và field.
- Business rejection không tạo ERROR trùng ở service và boundary.
- Terminal technical failure có **một event** và Throwable cause.
- Sensitive fields không xuất hiện.
- Nếu async, chờ completion một cách có giới hạn; không dựa vào sleep cố định.
- Test không để lại handler/global logger state ảnh hưởng test khác.

Trong JUL, logger handler là trạng thái toàn cục theo tên trong LogManager. Khi test thêm handler, nhớ **remove/close trong finally**, restore level/useParentHandlers nếu đã thay. Với Logback test appender, cũng cần detach và stop khi kết thúc.

### 17.3. Test transaction thực, không chỉ mock

Một unit test trên repository mock có thể thấy logger.info("created") chạy đúng, nhưng không kiểm tra commit. Với event "committed" hoặc audit quan trọng, dùng **integration test** có transaction manager thật và thử:

- Commit thành công.
- Lỗi flush/constraint violation gây rollback.
- Outer transaction rollback sau method return.
- Retry/duplicate hoặc callback after commit.
- Listener không được gọi khi rollback.

Không coi log text là bằng chứng duy nhất rằng database đã commit.

## 18. Chẩn đoán thực tế: một request tạo nhiều ERROR

Giả sử một request đặt hàng bị timeout inventory và dashboard xuất hiện **bốn record ERROR**.

### Bước 1: theo dấu cùng trace/request ID

Thu thập event theo cùng traceId/requestId, xem các logger names và timestamps. Xác định chúng có cùng cause chain/stack trace và cùng request không, hay là các attempts khác nhau.

### Bước 2: vẽ đường exception

~~~text
InventoryClient: timeout
    │
    ├── logger.error(..., ex)  [bản 1]
    ▼
OrderService catch + log.error [bản 2]
    ▼
OrderController catch + log.error [bản 3]
    ▼
GlobalExceptionHandler log.error [bản 4]
~~~

Nếu không có hành động xử lý nào tại các tầng giữa, bốn bản là **overlogging**. Không nên làm "giảm alert" bằng cách tắt ERROR toàn ứng dụng; sửa nơi sở hữu log terminal.

### Bước 3: thống nhất owner

Ví dụ chỉ **GlobalExceptionHandler** log terminal ERROR. InventoryClient có thể ghi metric/network attempt data; service thêm error code/cause khi wrap; controller không ghi lặp.

### Bước 4: giữ business event thật sự cần thiết

Nếu service có một quyết định fallback, retry exhausted hoặc invariant riêng, vẫn có thể log sự kiện đó ở INFO/WARN mà **không in lại cùng stack trace**. Như vậy truy vết không mất nghĩa nghiệp vụ.

### Bước 5: viết regression test

Kiểm tra **1 terminal error event / logical request** tại boundary đã chọn, cùng cause, errorCode và traceId; nếu multiple retries, test riêng số attempts và mức log. Không đo số lỗi bằng số dòng ERROR khi pipeline có thể ghi duplicate.

## 19. Những lỗi phổ biến

**1. Log rồi throw ở mọi tầng.** Dẫn đến stack trace trùng, mất tín hiệu và tăng chi phí.

**2. Chỉ log ex.getMessage() rồi bỏ Throwable.** Mất stack trace/cause chain cần cho debug; có thể lộ dữ liệu từ message.

**3. Trả null hoặc Optional.empty sau khi nuốt lỗi kỹ thuật.** Khi business contract không cho phép, lỗi bị che giấu và boundary có thể trả thành công giả.

**4. Log "success/committed" trước transaction commit.** Gây hiểu nhầm nếu transaction rollback.

**5. Log ERROR cho mọi business exception.** Hết hàng hoặc conflict dự kiến không nhất thiết là lỗi hệ thống.

**6. Log INFO cho mọi getter/method.** Tăng volume, ảnh hưởng hiệu năng và làm loãng log quan trọng.

**7. Đưa HTTP status vào mọi log service.** Service có thể chạy từ scheduler/consumer; status thuộc HTTP boundary.

**8. Log input/DTO bằng toString() không kiểm soát.** Rủi ro secret/PII và thông tin quá dài.

**9. Dùng string concatenation khi message đã có template logger.** Mất tối ưu lazy formatting và dễ lẫn dữ liệu đầu vào với cú pháp log.

**10. Không có error code/event name ổn định.** Phụ thuộc vào chuỗi tiếng Anh/Việt thay đổi theo version để query.

**11. Bỏ trace/correlation ID khi chuyển thread.** Khó ghép log; ThreadLocal context cũng có thể rò nếu không cleanup.

**12. Cho rằng logging là audit/event store bền vững.** Queue, crash, filesystem, collector và retention đều có thể làm mất event.

**13. Log nhiều lần trong retry rồi đếm thành nhiều lỗi độc lập.** Cần attempt ID và terminal outcome.

**14. Chỉ kiểm tra controller advice.** Background consumer, async task hoặc filter ngoài controller có boundary khác.

**15. Ghi exception message của bên thứ ba mà không đánh giá bảo mật.** Có thể chứa secret hoặc chuỗi gây log forging.

**16. Không cleanup test handler/appender.** Test sau bị nhận thêm event, tưởng production có duplicate logging.

**17. Ghi stack trace ERROR trước khi fallback thành công.** Chẩn đoán rất nhiễu; ưu tiên event retry/fallback có mức và context phù hợp.

**18. Dùng log để thay metric ở workload tải cao.** Mỗi method call không cần INFO; đặt metric hoặc trace span ở mốc hợp lý.

## 20. Checklist thiết kế log trong service

Trước khi merge code có thêm logger ở service, kiểm tra:

1. **Mục đích:** event này giúp ai điều tra quyết định nào?
2. **Trách nhiệm:** service đã xử lý, retry/fallback hay quyết định nghiệp vụ gì? Hay chỉ catch-and-rethrow?
3. **Mức độ:** INFO/WARN/ERROR/DEBUG có phù hợp tần suất và semantics không?
4. **Không trùng:** exception này sẽ được tầng nào log terminal? Có hơn một stack trace không?
5. **Transaction:** message có khẳng định điều chưa commit hoặc chưa ACK không?
6. **Context:** có event name, error code, service, traceId/requestId, attempt và các IDs cần thiết không?
7. **Bảo mật:** có token, password, PII, raw body, exception message không tin cậy không?
8. **Định dạng:** có structured encoder/escaping và giới hạn kích thước?
9. **Backend:** SLF4J có provider đúng, JUL/Logback/Log4j2 có appender/handler được bật và level phù hợp?
10. **Độ tin cậy:** event có bắt buộc giữ không? Nếu có, liệu có cần outbox/audit store thay vì logger?
11. **Hiệu năng:** event có phát ở hot path hoặc retry với lưu lượng rất lớn không?
12. **Kiểm thử:** có assert đúng số event/level/fields, cause và không ghi thừa?

## 21. Câu hỏi ôn luyện

1. Một OrderService bắt SQLException, ghi ERROR rồi ném lại; controller cũng ghi ERROR. Nên sửa ở đâu và vì sao?
2. Khi service fallback sang cache sau timeout và trả thành công, boundary có log được timeout ban đầu không? Service nên ghi gì?
3. Tại sao "order.created" trong @Transactional method có thể sai ngay cả khi repository.save trả về?
4. Vì sao service exception không nên tự chứa HTTP status trong mọi trường hợp?
5. Với SLF4J, điều gì khác nhau giữa log error kèm Throwable và chỉ ghi ex.getMessage()?
6. Một business exception OUT_OF_STOCK có cần log ERROR không? Nêu tiêu chí chọn level.
7. Vì sao MDC/requestId có thể bị thiếu khi tác vụ chuyển sang ExecutorService?
8. Một scheduled job gọi cùng OrderService thất bại nhưng @RestControllerAdvice không chạy. Ai phải sở hữu terminal error log?
9. Sự kiện chuyển trạng thái thanh toán bắt buộc không được mất: tại sao chỉ ghi INFO không đủ và nên dùng cơ chế gì?
10. Làm thế nào dùng test appender để chứng minh một failure chain chỉ có một terminal stack trace log?

## 22. Kết luận

**Log ở service đúng cách là ghi những quyết định nghiệp vụ và kết quả xử lý mà service thực sự sở hữu; không phải log mọi lời gọi hay mọi exception.** Với lỗi chưa được xử lý, hãy truyền exception có cause/context rõ và để boundary phù hợp ghi terminal failure **một lần**. Khi service xử lý retry/fallback hoặc đưa ra quyết định từ chối có ý nghĩa, service có thể ghi event độc lập ở mức phù hợp.

Hãy nhớ ba ranh giới: **service biết nghiệp vụ**, **entry point biết kết quả cuối**, còn **transaction manager biết commit/rollback**. Log message phải phản ánh đúng ranh giới đó. Kết hợp event name ổn định, structured fields, trace context, redaction, kiểm thử và cơ chế outbox/audit riêng cho sự kiện có yêu cầu bền vững để log thực sự hữu ích và đáng tin cậy.

### Tài liệu tham khảo

- Oracle JDK 17 — java.util.logging.Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle JDK 17 — Handler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html
- SLF4J Manual — Logger và fluent logging: https://www.slf4j.org/manual.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework — Declarative Transaction Rollback: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Exception Handling trong MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OpenTelemetry Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/