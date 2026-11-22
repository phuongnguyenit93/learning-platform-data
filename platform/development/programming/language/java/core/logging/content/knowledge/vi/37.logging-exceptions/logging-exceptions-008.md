# Business error trong Java: phân loại exception và ghi log đúng ngữ nghĩa nghiệp vụ

## 1. Business error là gì?

**Business error** (lỗi nghiệp vụ, lỗi quy tắc miền) là trường hợp một yêu cầu **không thể hoàn tất theo quy tắc nghiệp vụ đã định nghĩa**, mặc dù ứng dụng và hạ tầng có thể vẫn đang hoạt động bình thường. Ví dụ:

- Khách hàng đặt số lượng sản phẩm vượt tồn kho cho phép.
- Đơn hàng đã giao nên không thể hủy.
- Số dư không đủ để thực hiện chuyển tiền.
- Mã giảm giá đã hết hạn hoặc không áp dụng với giỏ hàng hiện tại.
- Người dùng không có quyền thực hiện một thao tác nhạy cảm.
- Một thao tác idempotent được gửi lại khi trạng thái đã đúng như yêu cầu.

Không phải trường hợp nào cũng là “exceptional failure” về mặt kỹ thuật. Ứng dụng có thể **đúng** khi từ chối yêu cầu. Trong code Java, business error có thể được biểu diễn bằng exception có kiểu, một kiểu `Result`/`Either`, hoặc kết quả validation — lựa chọn phụ thuộc kiến trúc, mức độ thường xuyên và cách viết API.

Ví dụ:

```text
Yêu cầu: Hủy đơn hàng O-100
Điều kiện: Đơn hàng đã SHIPPED
Kết quả: REJECTED, reasonCode=ORDER_ALREADY_SHIPPED
Hệ thống: Vẫn vận hành đúng, không có lỗi hạ tầng
```

Nếu log trường hợp này là:

```text
ERROR Critical system failure!!! java.lang.IllegalStateException: ...
```

thì dashboard sẽ tạo nhiễu, các đội vận hành dễ nhầm sang incident hệ thống, và chi phí stack trace có thể tăng vô ích. Một thông điệp phù hợp hơn thường là:

```text
INFO action=ORDER_CANCEL outcome=REJECTED reasonCode=ORDER_ALREADY_SHIPPED
     requestId=req-17 orderId=O-100
```

Mức `INFO` ở đây là **ví dụ chính sách**, không phải bắt buộc cho mọi tổ chức. Nếu hành vi từ chối quyền lặp lại bất thường hoặc có nguy cơ bảo mật, cùng loại sự kiện có thể cần phát vào **security audit** và một alert riêng. Severity dựa trên **tác động vận hành và mục đích quan sát**, không chỉ vì code đã `throw` exception.

### Trọng tâm của logging

Một log business error có ích cần trả lời:

1. **Điều gì đã được yêu cầu?** `action` và tài nguyên.
2. **Kết quả gì?** `REJECTED`, `DENIED`, `NO_CHANGE`, `FAILED` hoặc trạng thái chính xác khác.
3. **Vì sao?** `reasonCode` ổn định, không phải message tự do.
4. **Thao tác có để lại tác dụng phụ không?** Không có thay đổi, đã rollback, có thay đổi một phần, hay kết quả chưa xác định.
5. **Làm sao liên kết yêu cầu?** `requestId`/`operationId` được validate.
6. **Có cần cảnh báo?** Dựa trên tỷ lệ/ý nghĩa, tránh biến mọi từ chối hợp lệ thành `ERROR`.

**Business error không đồng nghĩa bug, crash hay log level ERROR.** Nó phản ánh một nhánh nghiệp vụ phải được thiết kế, trả về kết quả và quan sát nhất quán.

## 2. Business error, technical error và programming error khác nhau thế nào?

| Loại | Ví dụ | Cách xử lý thông thường | Logging gợi ý |
| --- | --- | --- | --- |
| **Business rule violation** | Hủy đơn đã giao, vượt hạn mức | Kết quả từ chối có mã được xác định | `INFO` hoặc `WARN` tùy rủi ro, thường không cần full stack |
| **Validation error** | Trường bắt buộc thiếu, giá trị sai schema | Trả kết quả validation; không mutation | Có thể không log từng lỗi; aggregate metric, audit khi cần |
| **Authorization denied** | Actor không có quyền đổi role | Từ chối; có thể cần audit bảo mật | Kênh audit có kiểm soát; WARN khi chính sách đòi hỏi |
| **Conflict/idempotency** | Version stale, trạng thái đã đạt | `CONFLICT` hoặc `NO_CHANGE` theo API contract | Log context ngắn, đừng coi mặc định là incident |
| **Technical/infrastructure failure** | Database không truy cập được, disk full, timeout dependency | Retry có kiểm soát hoặc fail/UNKNOWN | `ERROR` tại boundary chịu trách nhiệm; trace có chọn lọc |
| **Programming defect** | `NullPointerException` do invariant bị phá, index sai | Fail nhanh, sửa mã nguồn | Error + stack và context an toàn |
| **Unknown distributed outcome** | Timeout sau khi gửi lệnh thanh toán | Đối soát trước khi retry | `WARN/ERROR` theo tác động; `UNKNOWN`, không kết luận thất bại chắc |
| **Expected cancellation** | Người dùng hủy job chưa chạy | Kết quả `CANCELED` | Có thể `INFO` hoặc audit, không cần stack |

Ví dụ `IllegalArgumentException` không tự nói nó là lỗi nghiệp vụ. Nó có thể là một validation hợp lệ **hoặc** báo bug lập trình tùy nơi ném và hợp đồng. Do đó **không nên phân loại chỉ bằng tên exception hoặc mã HTTP**.

Một số nguyên tắc:

- Nếu lỗi được dự kiến trong thao tác hàng ngày và client có cách sửa, ưu tiên **reason code ổn định** và kết quả có cấu trúc.
- Nếu một invariant bên trong mà code cam kết luôn đúng bị phá, đó có thể là **bug**, không nên bị chuyển thành “khách hàng nhập sai”.
- Lỗi dependency thường cần thông tin chẩn đoán, retry policy, circuit breaker và theo dõi tình trạng.
- Khi side effect có thể đã diễn ra, không ghi `FAILED/ROLLED_BACK` trước khi xác minh; cân nhắc `UNKNOWN` hoặc `PARTIAL`.

## 3. Định nghĩa bộ mã lỗi nghiệp vụ

Không nên để client hoặc dashboard phải parse:

```text
"Order cannot be cancelled because it has already been shipped."
```

để đoán loại lỗi. Thông điệp này có thể thay đổi ngôn ngữ, cấu trúc hoặc cách đặt câu.

Định nghĩa một **bộ mã** theo miền:

| `reasonCode` | Ý nghĩa | Kết quả gợi ý | Retry tự động? |
| --- | --- | --- | --- |
| `ORDER_ALREADY_SHIPPED` | Đã giao, không thể hủy | `REJECTED` | Không |
| `INSUFFICIENT_STOCK` | Không đủ tồn kho theo quy tắc | `REJECTED` | Chỉ sau thay đổi điều kiện |
| `CREDIT_LIMIT_EXCEEDED` | Vượt hạn mức | `REJECTED` | Không retry nóng |
| `ORDER_NOT_FOUND` | Không có đối tượng theo ngữ cảnh quyền được phép công bố | `REJECTED` | Không, trừ khi dữ liệu eventual |
| `ALREADY_CANCELLED` | Đã ở trạng thái cần đạt | `NO_CHANGE` | Không cần |
| `POLICY_DENIED` | Bị từ chối theo quyền | `DENIED` | Không |
| `VERSION_CONFLICT` | Optimistic concurrency conflict | `CONFLICT/REJECTED` | Có thể retry có điều kiện |
| `DEPENDENCY_UNAVAILABLE` | Sự cố dịch vụ/DB | `FAILED/UNKNOWN` | Theo chính sách kỹ thuật |

Một mã lỗi cần có **một ý nghĩa được quản lý**; tránh để cùng mã mang hai nghĩa khác nhau trong các service. Có thể có thêm nhóm mã rộng, chẳng hạn `ORDER_`, `PAYMENT_`, `AUTH_`, nhưng đừng tạo mã quá chi tiết làm lộ dữ liệu nội bộ hoặc tăng cardinality không kiểm soát.

### Phân biệt mã lỗi và message

- `code`: ổn định, phục vụ API, logic, metric, phân tích.
- `publicMessage`: thân thiện, an toàn, có thể bản địa hóa; không tiết lộ bí mật.
- `technicalDetails`: thông tin chỉ dành cho chẩn đoán nội bộ, giới hạn truy cập và không đưa vào mọi log.
- `correlationId`: nối request của client với log/trace, không chứa token.

Không dùng `exception.getMessage()` làm `reasonCode`. Thông điệp có thể chứa SQL, đường dẫn, email, giá trị người dùng hoặc dấu xuống dòng; về lâu dài cũng không ổn định cho truy vấn.

## 4. Một business error nên được log ở mức nào?

**Không có ánh xạ tuyệt đối exception → ERROR.** Severity là quyết định về khả năng quan sát.

| Tình huống | Mức log thường cân nhắc | Có cần stack trace? |
| --- | --- | --- |
| Input validation bị từ chối thường xuyên | Không log từng case hoặc `DEBUG` | Thường không |
| Hủy đơn sau khi đã giao | `INFO` khi cần theo dõi, hoặc audit | Thường không |
| Hạn mức thanh toán không đủ | `INFO`/audit theo chính sách | Thường không |
| Access denied | Audit bảo mật; `INFO/WARN` tùy nguy cơ | Không mặc định |
| Conflict do optimistic locking dự kiến | `DEBUG/INFO` nếu số lượng lớn | Không mặc định |
| Business rule bị vi phạm bất thường, có tác động lớn | `WARN` và metric/alert | Có thể thêm context, chưa chắc cần stack |
| Database offline làm thao tác thất bại | `ERROR` ở boundary thích hợp | Thường có trace cho điều tra |
| Bug làm dữ liệu ở trạng thái không nhất quán | `ERROR`, incident | Có trace theo chính sách |

**Ví dụ một API có hàng nghìn request validation lỗi mỗi phút:** in stack trace đầy đủ cho mọi request gây tăng CPU, chi phí ingest, phí lưu log và nhiễu alert. Nên ghi count theo mã lỗi và tối thiểu hóa từng event, chỉ bật chẩn đoán chi tiết có phạm vi khi cần.

Tuy nhiên, **không phải cứ “business error” là bỏ qua**. Một số hành vi như từ chối giao dịch, truy cập trái phép, thay đổi cấu hình thất bại có thể là bằng chứng quan trọng. Có thể phát vào audit sink đáng tin cậy ngay cả khi không cảnh báo ERROR trên operational logger.

### Chọn mức log theo policy thay vì theo `catch`

Đoạn minh họa SLF4J:

```java
try {
    orderService.cancel(orderId);
} catch (OrderBusinessException ex) {
    logger.info(
        "action=ORDER_CANCEL outcome=REJECTED reasonCode={} orderId={}",
        ex.code(), safeOrderId);
    throw ex; // Hoặc map sang result ở boundary.
}
```

Đây là snippet trong dự án đã có các biến/class phù hợp, **không phải chương trình Java độc lập**. Nếu tầng trên lại ghi cùng lỗi, có thể tạo log trùng. Nên để một **boundary có trách nhiệm** chọn nơi ghi event kết quả, thay vì mọi tầng đều log.

## 5. Ghi log tại boundary: đừng log cùng một lỗi ở mọi layer

Một lỗi nghiệp vụ có thể đi qua controller → application service → domain service → repository. Nếu mỗi tầng đều `logger.error(..., ex)`, một sự kiện sẽ biến thành nhiều stack trace giống nhau.

Ví dụ chưa tốt:

```java
// Domain layer
throw new OrderBusinessException(ORDER_ALREADY_SHIPPED);

// Application layer
catch (OrderBusinessException e) {
    logger.error("Cannot cancel", e); // Trùng lần 1
    throw e;
}

// Web layer
catch (OrderBusinessException e) {
    logger.error("Request failed", e); // Trùng lần 2
    return conflictResponse(e);
}
```

Ví dụ là **pseudocode minh họa**, không có đầy đủ import/class/biến để biên dịch độc lập.

Một thiết kế phù hợp hơn:

1. **Domain layer:** xác định quy tắc, ném exception có mã hoặc trả result; thường không tự ghi log request.
2. **Application layer:** quyết định transaction, audit, trạng thái nghiệp vụ; bổ sung metadata cần thiết nếu có.
3. **Boundary** (HTTP handler, message consumer, scheduled job): map lỗi thành response/outcome và ghi **một event cấu trúc** có action, reasonCode và correlation ID.
4. **Observability layer:** thu thập metric/trace theo các mã, không lặp message/stack vô nghĩa.

Nguyên tắc **“log hoặc throw, đừng vừa log vừa throw ở mọi tầng”** là heuristic có ích, không phải luật tuyệt đối. Một tầng có thể ghi một event độc lập thật sự cần thiết (ví dụ timeout của attempt hay sự kiện audit), nhưng phải có **event type** riêng để tránh người đọc tưởng một lỗi xảy ra nhiều lần.

### Khi cần log exception gốc

Nếu business exception chỉ mang mã lỗi, log đủ mã + context, không cần `Throwable` toàn bộ. Nếu một technical failure có root cause cần điều tra, boundary chịu trách nhiệm có thể log exception một lần với stack trace và correlation ID, tránh cắt mất `cause`.

Đừng bao giờ đổi một exception chưa xác định thành business error chỉ để giảm mức `ERROR`: điều đó che bug và khiến SLA/alert bị sai.

## 6. Exception có kiểu hay Result object?

Có hai cách thiết kế thường gặp.

### 6.1. Exception cho trường hợp nghiệp vụ không hoàn tất

```java
public final class OrderBusinessException extends RuntimeException {
    private final String code;

    public OrderBusinessException(String code, String internalMessage) {
        super(internalMessage);
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

Lưu ví dụ này thành `OrderBusinessException.java` là một class Java hợp lệ. Trong dự án thật, nên dùng `enum`/`sealed hierarchy` khi hữu ích để giới hạn mã lỗi; không để client chọn `code` từ dữ liệu đầu vào.

**Ưu điểm:** dễ tích hợp với middleware/exception handler, tách nhánh happy path, propagate lỗi qua nhiều tầng.

**Đánh đổi:** exception có thể tạo stack trace lúc được khởi tạo; nếu dùng hàng trăm nghìn lần/giây cho những trạng thái rất thường gặp, chi phí cấp phát/capture stack có thể đáng kể. Exception cũng dễ bị `catch (Exception)` ở tầng ngoài map nhầm thành lỗi hệ thống nếu không phân loại đúng.

### 6.2. Kiểu kết quả rõ ràng cho những nhánh dự kiến

```java
// Java 17, ví dụ minh họa thiết kế kiểu.
sealed interface CancelResult
        permits CancelResult.Cancelled,
                CancelResult.NoChange,
                CancelResult.Rejected {

    record Cancelled() implements CancelResult {}
    record NoChange() implements CancelResult {}
    record Rejected(String reasonCode) implements CancelResult {}
}
```

Đây là kiểu dữ liệu hợp lệ trong Java 17 nếu đặt trong ngữ cảnh khai báo phù hợp. Caller xử lý từng kết quả rõ ràng, không cần tạo exception cho một trạng thái có thể dự kiến. Tuy nhiên, `Result` không tự bảo đảm caller xử lý đầy đủ nhánh, không tự tạo transaction, và cũng không tự ghi audit. Nếu API/middleware hiện có dùng exception có kiểu, giữ nhất quán quan trọng hơn đổi phong cách chỉ vì tránh stack.

### Chọn cách nào?

- **Validation thường xuyên:** trả lỗi có cấu trúc/`Result` thường phù hợp, không cần ném exception để điều khiển luồng.
- **Quy tắc miền khiến thao tác không thể hoàn tất:** có thể dùng business exception có mã hoặc `Result`, miễn mapping nhất quán.
- **Sự cố kỹ thuật bất thường:** exception với `cause` và stack có giá trị chẩn đoán.
- **Hot path:** đo thực tế với profiler/JMH trước khi tối ưu dựa trên cảm giác.

Không xóa stack trace của mọi exception để giảm chi phí: với bug hoặc sự cố hạ tầng, stack là dữ liệu rất quan trọng để điều tra.

## 7. Ví dụ Java 17 chạy độc lập: cancel order và logging chính xác

Ví dụ sau dùng **`java.util.logging` (JUL)** có sẵn trong JDK. Ta mô phỏng năm request: một hủy thành công, một request idempotent không đổi, hai request bị từ chối bởi quy tắc nghiệp vụ, và một sự cố hạ tầng giả lập. Logger thử nghiệm chỉ in level/message và tên loại throwable để stdout xác định; **đây không phải formatter production**.

### 7.1. Mã nguồn `BusinessErrorLoggingDemo.java`

```java
import java.util.HashMap;
import java.util.Map;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class BusinessErrorLoggingDemo {
    enum Status { CREATED, SHIPPED, CANCELLED }

    enum Reason {
        ORDER_NOT_FOUND,
        ORDER_ALREADY_SHIPPED
    }

    static final class BusinessRuleException extends RuntimeException {
        private final Reason reason;

        BusinessRuleException(Reason reason) {
            super(reason.name());
            this.reason = reason;
        }

        Reason reason() {
            return reason;
        }
    }

    static final class DependencyUnavailableException
            extends RuntimeException {
        DependencyUnavailableException() {
            super("simulated storage unavailable");
        }
    }

    static final class OrderService {
        private final Map<String, Status> orders =
                new HashMap<>(Map.of(
                        "o-1", Status.CREATED,
                        "o-2", Status.SHIPPED));

        boolean cancel(String orderId) {
            if ("db-down".equals(orderId)) {
                throw new DependencyUnavailableException();
            }

            Status status = orders.get(orderId);
            if (status == null) {
                throw new BusinessRuleException(Reason.ORDER_NOT_FOUND);
            }

            if (status == Status.SHIPPED) {
                throw new BusinessRuleException(
                        Reason.ORDER_ALREADY_SHIPPED);
            }

            if (status == Status.CANCELLED) {
                return false;
            }

            orders.put(orderId, Status.CANCELLED);
            return true;
        }

        Status statusOf(String orderId) {
            return orders.get(orderId);
        }
    }

    private static final Logger LOG =
            Logger.getLogger("example.business.error");

    private static void handle(
            OrderService service, String requestId, String orderId) {
        try {
            boolean changed = service.cancel(orderId);
            String outcome = changed ? "SUCCEEDED" : "NO_CHANGE";
            String reason = changed
                    ? "CANCELLED" : "ALREADY_CANCELLED";

            LOG.info("action=ORDER_CANCEL outcome=" + outcome
                    + " reasonCode=" + reason
                    + " requestId=" + requestId);
        } catch (BusinessRuleException e) {
            // Nhánh nghiệp vụ được dự kiến: không in full stack.
            LOG.info("action=ORDER_CANCEL outcome=REJECTED"
                    + " reasonCode=" + e.reason()
                    + " requestId=" + requestId);
        } catch (DependencyUnavailableException e) {
            // Lỗi kỹ thuật: giữ Throwable để backend có thể ghi stack.
            LOG.log(Level.SEVERE,
                    "action=ORDER_CANCEL outcome=FAILED"
                    + " reasonCode=DEPENDENCY_UNAVAILABLE"
                    + " requestId=" + requestId, e);
        }
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler deterministic = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }

                String line = record.getLevel().getName()
                        + " " + record.getMessage();

                if (record.getThrown() != null) {
                    line += " throwable="
                            + record.getThrown()
                                    .getClass().getSimpleName();
                }

                System.out.println(line);
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };

        deterministic.setLevel(Level.ALL);
        LOG.addHandler(deterministic);
        try {
            OrderService service = new OrderService();

            handle(service, "req-1", "o-1");
            handle(service, "req-2", "o-1");
            handle(service, "req-3", "o-2");
            handle(service, "req-4", "unknown");
            handle(service, "req-5", "db-down");

            System.out.println("finalStatus="
                    + service.statusOf("o-1"));
        } finally {
            LOG.removeHandler(deterministic);
            deterministic.close();
        }
    }
}
```

Lưu file đúng tên, dùng JDK 17 hoặc mới hơn:

```bash
javac BusinessErrorLoggingDemo.java
java BusinessErrorLoggingDemo
```

**Stdout chính xác khi chạy riêng chương trình trên:**

```text
INFO action=ORDER_CANCEL outcome=SUCCEEDED reasonCode=CANCELLED requestId=req-1
INFO action=ORDER_CANCEL outcome=NO_CHANGE reasonCode=ALREADY_CANCELLED requestId=req-2
INFO action=ORDER_CANCEL outcome=REJECTED reasonCode=ORDER_ALREADY_SHIPPED requestId=req-3
INFO action=ORDER_CANCEL outcome=REJECTED reasonCode=ORDER_NOT_FOUND requestId=req-4
SEVERE action=ORDER_CANCEL outcome=FAILED reasonCode=DEPENDENCY_UNAVAILABLE requestId=req-5 throwable=DependencyUnavailableException
finalStatus=CANCELLED
```

### 7.2. Đọc kết quả

- **req-1:** đơn `o-1` ở trạng thái `CREATED`, hủy thành công; logger in `SUCCEEDED`.
- **req-2:** cùng đơn đã `CANCELLED`; không cần mutation lần nữa, logger in `NO_CHANGE`.
- **req-3:** đơn `o-2` đã `SHIPPED`, không cho hủy; `BusinessRuleException` được map thành `REJECTED` tại `INFO`.
- **req-4:** không có đơn trong mô hình; map thành `REJECTED/ORDER_NOT_FOUND`. Trong hệ thống có yêu cầu chống enumeration, response cho client có thể không nói đối tượng có tồn tại hay không; audit nội bộ vẫn phải theo quyền truy cập thích hợp.
- **req-5:** mô phỏng dependency không sẵn sàng; log ở `SEVERE` (tương tự nhóm lỗi nghiêm trọng trong JUL), có attached `Throwable`, không bị nhầm sang business rule.
- Dòng cuối xác minh hủy hợp lệ đầu tiên đã đổi trạng thái đơn.

**Lưu ý về output:** Handler `deterministic` chỉ in class name của throwable, **không in stack trace**. Trong hệ thống dùng ConsoleHandler/Logback formatter thông thường, exception được gắn vào log record có thể tạo thêm stack trace và format không cố định. Bản demo dùng formatter giản lược để làm rõ sự khác nhau giữa log kết quả và log chẩn đoán.

**Giới hạn của ví dụ:** `HashMap` hoạt động trong bộ nhớ một thread, không có database transaction, kiểm soát quyền, logging sink bền vững hay mã hóa. `BusinessRuleException` vẫn tạo stack trace khi khởi tạo dù test không in nó. Phần `db-down` là lỗi giả có chủ đích. Chương trình giúp hiểu classification và message, **không phải code production cho xử lý đơn hàng**.

## 8. Mapping business error ra HTTP/API

Trong ứng dụng HTTP, lỗi nghiệp vụ phải được map thành **một API contract nhất quán**, đồng thời log context nội bộ phù hợp. Một mẫu response:

```json
{
  "code": "ORDER_ALREADY_SHIPPED",
  "message": "Order cannot be cancelled at this stage.",
  "requestId": "req-3"
}
```

HTTP status phụ thuộc semantics:

| Điều kiện | HTTP thường cân nhắc | Outcome nội bộ |
| --- | --- | --- |
| Schema input không hợp lệ | `400 Bad Request` | `REJECTED` |
| Resource không tìm thấy và được phép thông báo | `404 Not Found` | `REJECTED` |
| Actor không đủ quyền | `403 Forbidden` | `DENIED` |
| Trạng thái hiện tại xung đột với yêu cầu | `409 Conflict` | `REJECTED`/`CONFLICT` |
| Vi phạm quy tắc miền dù request đúng cú pháp | `422 Unprocessable Content` hoặc `409` tùy contract | `REJECTED` |
| Idempotent đã đạt trạng thái mong muốn | Có thể `200/204` | `NO_CHANGE` |
| Dependency không khả dụng | `503 Service Unavailable` khi phù hợp | `FAILED/UNKNOWN` theo chứng cứ |
| Bug không kiểm soát | `500 Internal Server Error` | `FAILED`, error ID nội bộ |

**Không dùng mã HTTP đơn lẻ để kết luận outcome.** HTTP 500 sau khi đã commit có thể là lỗi encode response; HTTP 202 có thể chỉ xác nhận request được tiếp nhận, không phải job xong.

### Spring Boot `@RestControllerAdvice`: mã minh họa

```java
@RestControllerAdvice
class ApiErrorHandler {
    @ExceptionHandler(OrderBusinessException.class)
    ResponseEntity<ApiError> handleBusiness(
            OrderBusinessException ex,
            HttpServletRequest request) {

        String requestId = validatedRequestId(request);
        log.info("outcome=REJECTED reasonCode={} requestId={}",
                ex.reason(), requestId);

        ApiError body = new ApiError(
                ex.reason().name(),
                "Request cannot be completed.",
                requestId);

        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }
}
```

Đây **chỉ là snippet minh họa**, không độc lập: giả định có SLF4J `log`, `OrderBusinessException`, `ApiError`, `validatedRequestId` và các import Spring/Servlet thích hợp. Thực tế nên map **từng reasonCode** sang status phù hợp, không trả `409` cho mọi loại lỗi. Khi xác thực, không tin header request ID trực tiếp nếu chưa validate. API public nên dùng message an toàn, không gửi stack trace, SQL hoặc nội dung exception raw.

Nếu service layer đã log cùng `BusinessRuleException`, hãy chọn một điểm chịu trách nhiệm logging để tránh trùng. Nếu kênh audit cần ghi nhận mọi denied/rejected, đó có thể là event độc lập với access log ở web boundary.

## 9. Business error trong ứng dụng message hoặc job bất đồng bộ

Một message consumer nhận `CancelOrder` có thể thấy `ORDER_ALREADY_SHIPPED`. Đây có thể là lỗi **không thể chữa bằng retry**. Nếu consumer tự động NACK/requeue mãi, poison message sẽ chạy lại và spam log.

Phân loại theo khả năng hồi phục:

| Nhóm | Ví dụ | Hành động thường dùng |
| --- | --- | --- |
| Permanent business rejection | Đơn đã giao, mã giảm giá không hợp lệ | Ghi kết quả `REJECTED`, ACK hoặc DLQ theo contract, không retry nóng |
| Validation lỗi payload | Thiếu schema field bắt buộc | Reject/DLQ, cảnh báo producer, tránh vòng lặp |
| Transient technical | Network timeout, DB tạm không khả dụng | Retry với backoff, budget, idempotency |
| Unknown remote outcome | Thanh toán timeout sau khi phát lệnh | Đối soát/idempotency trước khi retry side effect |
| Idempotent duplicate | Message đã được xử lý cùng ID | Ghi `DEDUP/NO_CHANGE`, ACK theo contract |

**ACK** của broker chỉ nói tiến độ message theo giao thức, không chứng minh audit log đã bền vững. Lỗi nghiệp vụ được kết luận ở consumer cần có `messageId`, `operationId`, `attempt` và mã lý do để điều tra; không log raw payload chứa dữ liệu cá nhân.

Một luồng an toàn về ý nghĩa:

```text
Receive message
   |
   v
Validate + authorize + idempotency check
   |
   +-- Permanent business error --> record rejection --> ACK/DLQ theo policy
   |
   +-- Transient failure --------> retry scheduling/backoff
   |
   +-- Business effect commit ---> record outcome --> ACK
   |
   +-- Commit uncertain ---------> reconcile, không retry mù
```

Nếu business error **không phải terminal** trong một workflow cụ thể, ví dụ hết tồn kho nhưng cho phép backorder, policy có thể khác. Đừng gán mặc định “mọi business exception đều không retry”; quyết định dựa vào ý nghĩa miền, trạng thái có thể thay đổi và deadline.

## 10. Transaction, rollback và kết quả chính xác

Một nguy cơ lớn của business error logging là **tuyên bố sai kết quả**. Ví dụ:

```text
T1: Validation passed
T2: Ghi "SUCCEEDED" vào log
T3: UPDATE DB
T4: Transaction rollback do conflict
=> Log "SUCCEEDED" không phản ánh trạng thái cuối
```

Nếu một thao tác có thể commit và rollback, nên chốt outcome sau ranh giới thành công theo contract. Cần chú ý:

- Với transaction DB, `repository.save(...)` không tự là bằng chứng commit.
- Số hàng update hoặc optimistic locking có thể phát hiện conflict; không coi update 0 hàng là success.
- Khi transaction rollback vì business exception, event ghi trong **cùng DB transaction** cũng rollback. Nếu cần audit rejection/denied, dùng kênh riêng hoặc transaction audit độc lập.
- Nếu ngoại lệ xảy ra **sau commit**, không tự động đánh dấu thao tác `FAILED`. Có thể cần outcome `UNKNOWN` cho client nếu không xác minh được, và đối soát.
- Side effect ngoài DB không rollback cùng transaction local; nếu xảy ra một phần, dùng `PARTIALLY_SUCCEEDED`/compensation theo hợp đồng.

### Outcome và log severity vẫn là hai trục riêng

`outcome=REJECTED` có thể được ghi `INFO`; `outcome=SUCCEEDED` có thể được lưu qua audit store chuyên dụng; `outcome=FAILED` vì timeout có thể cần `WARN/ERROR` và đối soát.

Không đặt tất cả log business error ở catch/finally rồi mặc định rollback. **Hành vi commit, transaction boundary và loại lỗi quyết định sự thật**, còn logger chỉ ghi lại sự thật đó.

## 11. Audit logging: từ chối hợp lệ cũng có thể quan trọng

Một lỗi nghiệp vụ có thể không phải sự cố kỹ thuật, nhưng vẫn cần bằng chứng kiểm toán, nhất là:

- Truy cập và thay đổi quyền bị từ chối.
- Thao tác thanh toán/trừ tiền không được cho phép.
- Thay đổi cấu hình/khóa bảo mật thất bại.
- Quyết định của policy, hạn mức hoặc kiểm soát chống gian lận.
- Từ chối giao dịch để tuân thủ quy định.

Một audit event có thể là:

```json
{
  "eventType": "BUSINESS_OPERATION_RESULT",
  "action": "ORDER_CANCEL",
  "actorId": "user-19",
  "resourceId": "order-100",
  "operationId": "op-72",
  "outcome": "REJECTED",
  "reasonCode": "ORDER_ALREADY_SHIPPED",
  "occurredAt": "2026-01-01T10:00:00Z"
}
```

JSON chỉ là dữ liệu ví dụ. Đừng dùng `INFO` của một AsyncAppender best-effort làm bảo đảm audit quan trọng nếu chính sách đòi hỏi độ bền. Khi cần, dùng audit repository/outbox hoặc sink có acknowledgment, quyền truy cập/retention phù hợp.

**Không đánh đồng business rejection với alert bảo mật.** Hệ thống có thể từ chối rất nhiều request hợp lệ; để phát hiện tấn công cần kết hợp actor, target, tần suất, dấu hiệu và nguồn đáng tin. Đồng thời hạn chế thông tin trong API response để tránh attacker dùng reason code suy đoán tài nguyên nhạy cảm.

## 12. SLF4J và structured logging cho business error

Trong hệ thống dùng SLF4J, nên ghi trường ổn định:

```java
// Snippet trong ứng dụng đã có logger, requestId, orderId, code.
logger.info(
    "action={} outcome={} reasonCode={} requestId={} orderId={}",
    "ORDER_CANCEL", "REJECTED", code, requestId, orderId);
```

Parameterized logging tránh nối chuỗi eager trong một số trường hợp, nhưng **không tự mask secret** hoặc biến message thành JSON. Nếu parser downstream cần truy vấn `reasonCode` hoặc `outcome`, nên dùng structured logging/JSON encoder phù hợp backend; xác minh key/type/schema trên sink thực tế.

### Một số trường nên có

| Trường | Mục đích | Cách sử dụng |
| --- | --- | --- |
| `eventType` | Loại event: `BUSINESS_RULE_REJECTED` | Giúp query chính xác |
| `action` | `ORDER_CANCEL`, `PAYMENT_TRANSFER` | Tránh message tự do |
| `outcome` | `REJECTED`, `NO_CHANGE`, `FAILED` | Phản ánh kết quả đã xác minh |
| `reasonCode` | Mã lỗi miền | Không dùng raw exception message |
| `requestId`/`traceId` | Liên kết request | Không mang token |
| `operationId` | Liên kết các attempt của thao tác logic | Giữ ổn định qua retry |
| `resourceId` | Tài nguyên liên quan | Kiểm soát quyền riêng tư |
| `durationMs` | Độ trễ ở boundary xác định | Không dùng làm bằng chứng commit |
| `service`, `environment` | Nguồn phát | Tránh cardinality bất hợp lý |
| `retryable` | Quyết định có thể thử lại | Tính theo chính sách, không chỉ tên exception |

Không nhất thiết ghi mọi trường ở mọi event. Chọn đủ để điều tra và tối thiểu hóa dữ liệu.

### MDC và context propagation

Trong ứng dụng đa thread, MDC có thể chứa request/operation ID để gắn vào log:

```java
// Minh họa cho ứng dụng có SLF4J và các biến an toàn.
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("requestId", validatedRequestId);
    processBusinessCommand();
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

Đoạn này không độc lập: cần import `Map`, `MDC` và có phương thức/biến tương ứng. MDC thường gắn với thread hiện tại; `CompletableFuture`, thread pool hoặc reactive pipeline không nhất thiết tự lan truyền nó. Không `clear/restore` có thể khiến business error của request B bị gắn nhầm ID của request A.

Tránh đặt `password`, `accessToken`, raw request body hoặc secret trong MDC: các appender có thể xuất toàn bộ context theo pattern mà developer không để ý.

## 13. Bảo mật: không biến business error thành nguồn lộ dữ liệu

Business exception có thể chứa tham số từ người dùng:

```java
throw new BusinessRuleException(
        "Invalid card " + fullCardNumber);
```

Nếu tầng web log nguyên exception message hoặc stack, số thẻ có thể chảy vào file, collector, dashboard, backup và export. Tốt hơn là:

```text
reasonCode=PAYMENT_METHOD_REJECTED
paymentMethodRef=pm_opaque_42
requestId=req-42
```

Với thông điệp trả client, chỉ cung cấp mã và mô tả phù hợp; không đưa SQL, query, internal path, stack trace hoặc thông tin về đối tượng mà actor không có quyền xem.

**Log injection:** trường do client cung cấp có thể chứa `\r`, `\n` hoặc ký tự điều khiển nhằm tạo dòng giả. Dùng encoder có escaping đúng, validate correlation ID và giới hạn chiều dài. Không tin một chuỗi bất kỳ là ID an toàn chỉ vì tên field là `requestId`.

Một số ứng dụng dùng `toString()` trên DTO trong log:

```java
logger.warn("Rejected transfer {}", transferRequest);
```

Nếu DTO chứa tài khoản, token hoặc PII, object serialization có thể lộ dữ liệu. Log **allowlist các field đã đánh giá**, không log nguyên object chỉ để tiện debug. Hash không tự làm PII vô hại: định danh có miền nhỏ vẫn có thể bị suy ngược.

## 14. Hiệu năng: exception thường gặp và chi phí stack trace

Tạo một `Throwable` thông thường thường capture thông tin call stack tại thời điểm khởi tạo. Vì vậy, dùng exception như cơ chế điều khiển luồng thường xuyên có thể tạo chi phí dù ta không in stack.

Một số lựa chọn:

- Nếu validation là nhánh xảy ra rất nhiều, dùng `Result`/validation report có thể giảm chi phí và giúp API contract rõ hơn.
- Nếu business exception có ý nghĩa hiếm gặp, chi phí thường không đáng kể so với hoạt động DB/network; đo trước khi tối ưu.
- Tránh `logger.error("Business failed", ex)` trên mỗi lỗi quy tắc thường gặp nếu không cần trace.
- Khi `DEBUG` đang tắt, biểu thức argument như `new Exception(...)` **vẫn được Java đánh giá** trước lời gọi logger. Dùng guard hoặc lazy supplier phù hợp nếu tạo thông tin chẩn đoán đắt.
- Khi đã có exception thật, đừng gọi `getStackTrace()`, format thêm String và lại truyền cùng exception cho backend: dễ nhân đôi chi phí mà không tăng thông tin.

Không xóa stack trace khỏi mọi custom exception chỉ để cải thiện microbenchmark; việc mất dấu nơi phát sinh bug có thể đắt hơn. JMH/profiler, allocation rate, p95/p99 và thực tế error rate mới giúp quyết định có cần tối ưu không.

## 15. Log lỗi nghiệp vụ trong quy trình retry và idempotency

Một client có thể gửi lại request vì timeout, hoặc message broker redeliver sau khi ACK mất. Một thao tác đã thành công lần đầu có thể bị gọi lại khi dữ liệu đã đổi. Khi đó **log đúng outcome** quan trọng hơn in exception.

Ví dụ:

```text
operationId=op-9 attempt=1 -> SUCCEEDED, order canceled
operationId=op-9 attempt=2 -> NO_CHANGE, already canceled
logical operation outcome -> SUCCEEDED
```

Nếu một request thứ hai cùng resource nhưng **operation ID khác**, việc `NO_CHANGE` có thể vẫn đúng, nhưng không mặc định đó là “retry của cùng operation”. Phân biệt `requestId`, `operationId`, `attemptId` và event ID.

Đối với lỗi business không retry được như `ORDER_ALREADY_SHIPPED`, retry tự động liên tục sẽ tạo log flooding. Với lỗi transient như `DEPENDENCY_UNAVAILABLE`, có thể retry theo backoff, timeout, budget và idempotency. Với timeout sau side effect chưa rõ, phải đối soát; không coi `FAILED` và retry là luôn an toàn.

### Xác định thành công theo phạm vi

Một worker có thể log `MESSAGE_ACK_REQUESTED` sau khi xử lý. Nhưng việc ACK được broker chấp nhận và việc audit event được collector lưu **là hai kết quả khác nhau**. Nếu business error có yêu cầu lưu audit, cần hợp đồng lưu riêng.

Trong hệ thống nhiều bước hoặc saga, một bước business error có thể khiến workflow chạy compensation. Ghi nhận cả attempt ban đầu, lỗi, compensation và kết quả cuối; không ghi đè lịch sử bằng một event `FAILED` duy nhất.

## 16. Kiểm thử business error logging

Không đủ để assert `throw BusinessRuleException` hoặc `verify(logger).warn(...)`; phải kiểm tra **outcome và tác dụng phụ thực tế**.

### Ma trận kiểm thử gợi ý

| Tình huống | Trạng thái nghiệp vụ | Event kỳ vọng | Mức/chú ý |
| --- | --- | --- | --- |
| Hủy đơn được phép | Đã chuyển `CANCELLED` | `SUCCEEDED/CANCELLED` | `INFO` theo policy |
| Hủy lại đơn đã hủy | Không đổi | `NO_CHANGE/ALREADY_CANCELLED` | Không báo lỗi giả |
| Đơn đã giao | Không đổi | `REJECTED/ORDER_ALREADY_SHIPPED` | Không full stack bắt buộc |
| Đơn không tồn tại | Không đổi | `REJECTED/ORDER_NOT_FOUND` | Không lộ thông tin vượt quyền |
| Không đủ quyền | Không đổi | `DENIED/POLICY_DENIED` | Cần audit nếu policy yêu cầu |
| Lỗi DB trước mutation | Không đổi | `FAILED/DEPENDENCY_UNAVAILABLE` | Có trace/error ID phù hợp |
| Timeout sau khi có thể đã commit | Chưa rõ | `UNKNOWN/RESULT_UNCONFIRMED` | Đối soát |
| Concurrent update conflict | Update không được chấp nhận | `REJECTED/CONFLICT` | Kiểm tra version/row count |
| Job được nhận để chạy | Chưa xong | `PENDING` | Sau đó có terminal event |
| Bulk có 8/10 commit | Có 8 tác dụng phụ | `PARTIALLY_SUCCEEDED` | Ghi số lượng và liên kết item |

### Kiểm thử ở các tầng

1. **Domain/unit:** business rule cho đúng code, không mutation khi bị từ chối, case `NO_CHANGE` rõ ràng.
2. **Application/integration:** transaction thực sự commit/rollback, outcome theo trạng thái cuối.
3. **Web/message boundary:** mã HTTP/NACK/ACK hoặc result và nội dung log theo schema; không log lặp ở tầng dưới.
4. **Audit delivery:** sự kiện quan trọng được lưu theo hợp đồng, xử lý mất collector/retry/dedup phù hợp.
5. **Security:** exception message, MDC, DTO `toString()` không lộ token/PII, input CR/LF không tạo log giả.
6. **Concurrency/retry:** request song song, optimistic versioning, idempotency key và correlation context không rò chéo.

### Ví dụ JUnit 5 về mapping business exception

Đoạn dưới là **test minh họa** dùng JUnit Jupiter; cần đặt cùng package với `BusinessErrorLoggingDemo` hoặc chỉnh visibility theo dự án và có JUnit trên classpath, không phải class chạy độc lập:

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class BusinessErrorTest {
    @Test
    void cannotCancelShippedOrder() {
        var service = new BusinessErrorLoggingDemo.OrderService();

        var ex = assertThrows(
                BusinessErrorLoggingDemo.BusinessRuleException.class,
                () -> service.cancel("o-2"));

        assertEquals(
                BusinessErrorLoggingDemo.Reason.ORDER_ALREADY_SHIPPED,
                ex.reason());
        assertEquals(
                BusinessErrorLoggingDemo.Status.SHIPPED,
                service.statusOf("o-2"));
    }

    @Test
    void secondCancelIsNoChange() {
        var service = new BusinessErrorLoggingDemo.OrderService();

        assertTrue(service.cancel("o-1"));
        assertFalse(service.cancel("o-1"));
    }
}
```

Hai test mới kiểm tra **domain behavior**. Muốn assert log thật, có thể gắn in-memory JUL Handler/Logback ListAppender và so message/level/context; phải gỡ appender và restore state sau test để không làm nhiễu test suite.

Nếu backend logging bất đồng bộ, đợi event bằng `BlockingQueue.poll(timeout)` hoặc latch/sink acknowledgment; không suy event đã đến chỉ vì gọi logger xong hoặc `Thread.sleep` một khoảng cố định.

## 17. Metric và cảnh báo với business error

Business errors có thể nhiều nhưng phần lớn là hệ thống đang bảo vệ quy tắc đúng. Metric phải **phân biệt hành vi mong đợi với lỗi hạ tầng**.

Tên metric minh họa:

| Metric | Mục đích |
| --- | --- |
| `business_operations_total{action,outcome}` | Phân bố kết quả theo action |
| `business_rejections_total{reasonCode}` | Xem loại business rejection nào tăng |
| `technical_failures_total{dependency}` | Theo dõi sự cố hạ tầng riêng |
| `business_operation_duration_seconds` | Theo dõi latency theo outcome |
| `audit_delivery_errors_total` | Tách lỗi ghi audit khỏi lỗi business |
| `business_unknown_outcomes` | Số thao tác cần đối soát |
| `retry_attempts_total{reasonGroup}` | Tìm retry loop |
| `business_conflicts_total{action}` | Phân tích contention/optimistic locking |

Các tên trên không phải metric mặc định của SLF4J hoặc Logback. Khi triển khai Micrometer/Prometheus hay giải pháp khác, kiểm soát **cardinality**: không dùng `requestId`, `orderId`, tên người dùng hoặc message tự do làm label.

Không nhất thiết phát alert cho từng `ORDER_ALREADY_SHIPPED`. Tỷ lệ tăng đột biến, phân bố bất thường hoặc kết quả tác động nghiệp vụ lớn có thể là tín hiệu. Ví dụ nhiều `POLICY_DENIED` trên một tài nguyên nhạy cảm cần điều tra theo security policy; nhiều `VERSION_CONFLICT` có thể phản ánh concurrency cần tối ưu, không phải cuộc tấn công.

## 18. Các sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Bất kỳ exception đều log `ERROR` | Business rejection có thể là hoạt động bình thường | Phân loại theo taxonomy và tác động |
| Ghi stack trace cho mọi validation | CPU/GC/log cost cao, alert nhiễu | Code + context; stack cho lỗi kỹ thuật |
| `logger.error` trong service rồi throw để web log lại | Nhân bản cùng lỗi | Một boundary chịu trách nhiệm |
| Ghi `SUCCEEDED` trước transaction commit | Sai sự thật nếu rollback | Chốt sau xác minh hiệu lực |
| Bất kỳ timeout đều `FAILED` | Side effect có thể đã xảy ra | `UNKNOWN` + đối soát |
| Map tất cả `RuntimeException` sang business rejection | Che bug/hạ tầng | Catch đúng loại, unexpected vẫn là technical |
| Dùng message tự do làm mã lỗi | Khó query, thay đổi ngôn ngữ | `reasonCode` được quản lý |
| Trả nguyên exception cho client | Có thể lộ stack, SQL, token | Message public an toàn |
| Log toàn DTO `toString()` | Có thể chứa PII/secret | Allowlist trường được phép |
| Business exception bị retry vô hạn | Poison loop, spam log, tốn tài nguyên | Phân loại permanent/transient |
| Coi status HTTP là outcome cuối của job | `202` có thể mới nhận job | Lifecycle + operation ID |
| Không ghi denied vì không có mutation | Thiếu dấu vết bảo mật | Audit riêng theo policy |
| Chỉ test loại exception | Không biết state/commit/log có đúng | Test cả outcome, state và sink |
| Cho rằng `INFO` được lưu audit bền vững | Filter/async queue/collector có thể mất event | Audit store/outbox/ack nếu cần |

## 19. Checklist trước khi đưa vào production

- [ ] Đã thống nhất thế nào là business error, validation, technical failure và programming defect.
- [ ] Có `reasonCode` và `outcome` ổn định, không suy từ exception message.
- [ ] Mức log dựa trên nhu cầu vận hành, không gắn `ERROR` mặc định cho mọi `throw`.
- [ ] Business rejection dự kiến không bị log stack trace lặp ở nhiều tầng.
- [ ] Boundary chịu trách nhiệm mapping response/message và log context đúng mốc.
- [ ] `SUCCEEDED` không được ghi trước khi tác dụng nghiệp vụ được xác minh/commit.
- [ ] `UNKNOWN`/`PARTIALLY_SUCCEEDED` được dùng khi side effect chưa chắc hoặc chỉ một phần.
- [ ] Retry policy phân biệt lỗi thường trực với lỗi transient; có idempotency.
- [ ] Event có action, outcome, reason, ID tương quan; không có secret/PII ngoài chính sách.
- [ ] Audit/security event cần lưu được tách khỏi best-effort debug log khi phù hợp.
- [ ] Test xác minh domain state, error code, log level, message và transaction behavior.
- [ ] Có test failure injection với DB/collector, concurrent update và async logging.
- [ ] Monitoring phân biệt tỷ lệ business rejection với incident kỹ thuật, không làm nhiễu alert.
- [ ] Error schema và log schema được review/version khi đổi semantics.

**Ghi nhớ:** business error không có nghĩa hệ thống bị hỏng. Nó thường là **kết quả hợp lệ của một quy tắc nghiệp vụ**, cần trả về mã ổn định, ghi log đủ context và đúng mức, không nhân bản stack trace. Chỉ khi phân biệt được **yêu cầu bị từ chối** với **thao tác thất bại vì hạ tầng**, hệ thống logging mới giúp đội phát triển, vận hành và kiểm toán hiểu đúng điều đã xảy ra.
