# Thêm ngữ cảnh thao tác và định danh có ích cho điều tra lỗi trong Java

> **Chủ đề:** Java Core → Exception → Chẩn đoán và ghi log. Mục tiêu của bài là biến một thông báo ngoại lệ chung chung thành bằng chứng đủ để truy vết *thao tác nào thất bại, đối tượng nghiệp vụ nào liên quan, request/tác vụ nào phát sinh lỗi, hệ thống đang ở bước nào và nguyên nhân gốc là gì*; đồng thời tránh làm lộ dữ liệu nhạy cảm hoặc gây nhiễu bởi log trùng lặp.

## 1. Tại sao chỉ ghi exception message là chưa đủ?

Giả sử dịch vụ xử lý hàng nghìn đơn hàng cùng lúc và log duy nhất là:

~~~text
ERROR java.lang.IllegalStateException: timeout
~~~

Thông báo này không nói rõ lỗi xảy ra khi xác nhận đơn, thanh toán, giữ hàng hay gửi thông báo; không thể nối nó với một request, đơn hàng, tác vụ nền hoặc dependency cụ thể. Stack trace xác định **đường gọi mã**, nhưng chưa chắc cho biết **ngữ cảnh nghiệp vụ** khiến lỗi phát sinh.

Một sự kiện log hữu ích có thể biểu đạt:

~~~text
level=ERROR event=order_save_failed operation=place_order
requestId=req-7e21 orderId=ord-1042
errorCode=ORDER_PERSIST_FAILED dependency=orders-db
exception=OrderProcessingException
cause=SQLTransientConnectionException
~~~

Đây là log **minh họa**, không phải đầu ra từ code chạy bên dưới. Các định danh trong ví dụ là dữ liệu giả. Nhờ những trường đó, người điều tra có thể tìm các sự kiện liên quan cùng request, kiểm tra đơn hàng cụ thể, phân nhóm theo mã lỗi và đối chiếu lỗi với dịch vụ phụ thuộc.

**Nguyên tắc chính:** *exception giải thích quá trình thất bại trong mã; context giải thích thất bại thuộc công việc nào*. Cần cả hai, nhưng không nên nhồi mọi dữ liệu có thể lấy được vào message hoặc log.

## 2. Bốn nhóm ngữ cảnh nên cân nhắc

Không phải mọi lỗi cần mọi trường. Hãy chọn ngữ cảnh có ích cho điều tra đúng với ranh giới và hợp đồng của thao tác.

| Nhóm | Trường điển hình | Câu hỏi trả lời | Lưu ý |
|---|---|---|---|
| Thao tác | `operation`, `event`, `stage`, `component` | Đang làm việc gì, ở bước nào? | Ưu tiên tên ổn định, có nghĩa nghiệp vụ |
| Liên kết yêu cầu | `requestId`, `correlationId`, `traceId`, `spanId` | Các log nào cùng một luồng nghiệp vụ? | Tránh sinh lại ID tùy tiện qua mỗi tầng |
| Đối tượng nghiệp vụ | `orderId`, `jobId`, `paymentAttemptId`, `messageId` | Đơn/tác vụ/lần thử nào bị tác động? | Dùng ID tối thiểu, có kiểm soát truy cập |
| Chẩn đoán kỹ thuật | `errorCode`, `dependency`, `attempt`, `elapsedMs`, `exception.type`, `cause` | Hỏng vì đâu, có thể tái hiện và thống kê không? | Phân biệt bằng chứng đo được và suy đoán |

Các trường nên có định nghĩa rõ. Chẳng hạn `orderId` chỉ ra **đơn hàng**, trong khi `requestId` chỉ ra **một request xử lý**; một đơn có thể được xử lý bởi nhiều request. `messageId` có thể được xử lý lại nhiều lần, nên `attempt` hoặc `jobExecutionId` giúp phân biệt từng lần thực thi.

### Tên thao tác: đủ chính xác nhưng ổn định

Nên dùng `operation=reserve_inventory`, `operation=charge_payment`, `operation=publish_order_event` thay vì các tên mơ hồ như `process`, `run` hoặc tên method dễ thay đổi do refactor. Một tên operation ổn định giúp:

- Tổng hợp số lỗi theo chức năng.
- So sánh log trước/sau các bản phát hành.
- Tạo truy vấn và cảnh báo không phụ thuộc stack trace.
- Đối chiếu các chặng khác nhau của cùng một quy trình.

Không đưa toàn bộ URL chứa token hoặc nguyên văn SQL có thông tin khách hàng vào tên operation. Sử dụng tên dạng mẫu (route/template) nếu cần mô tả endpoint.

## 3. Phân biệt request ID, correlation ID, trace ID và business ID

Những trường này liên quan nhưng **không đồng nghĩa**.

- **Request ID:** nhận diện một lần nhận request ở ranh giới hệ thống; hữu ích để tìm log của một request cụ thể.
- **Correlation ID:** liên kết nhiều message, request hoặc bước nằm trong cùng một quy trình nghiệp vụ. Có hệ thống dùng chung request ID làm correlation ID, nhưng cần một quy ước nhất quán.
- **Trace ID:** nhận diện một distributed trace; nhiều span thuộc cùng trace. Khi đã có công cụ tracing, nên dùng trace ID do tracing system cung cấp, không tự phát minh một ID khác rồi gọi là `traceId`.
- **Span ID:** nhận diện một đoạn công việc trong trace. Có thể thay đổi giữa các chặng; không dùng nó thay cho ID xuyên toàn bộ trace.
- **Business ID:** mã đơn hàng, giao dịch, job hoặc đối tượng bị tác động. Một đối tượng có thể xuất hiện trong nhiều request/trace khác nhau.
- **Attempt/Execution ID:** nhận diện một lần thử thực hiện công việc, đặc biệt quan trọng với retry, batch, queue và task định kỳ.

Ví dụ một payment attempt có thể có:

~~~text
traceId=4bf92f3577b34da6a3ce929d0e0e4736
requestId=req-e9b3
orderId=ord-321
paymentAttemptId=pat-02
attempt=2
~~~

Giá trị `traceId` ở đây chỉ là ví dụ định dạng hex, không phải ID trích từ một hệ thống thật.

**Không tự động tin định danh đến từ client.** Nếu HTTP header cung cấp request/correlation ID, hệ thống nên kiểm tra độ dài, ký tự cho phép, định dạng, chính sách tin cậy và tránh log injection. Khi không có ID hợp lệ, tạo ID phía server theo quy ước rồi truyền qua các tầng liên quan.

## 4. Context nằm ở đâu: tham số, ngoại lệ hay logging context?

Có ba cách thường được kết hợp tùy kiến trúc.

### 4.1. Truyền đối tượng context rõ ràng

~~~java
// Đoạn minh họa trong Java 17.
record OperationContext(
        String operation,
        String requestId,
        String orderId) {
}
~~~

Sau đó các tầng nhận `OperationContext context` như một tham số. Cách này thể hiện phụ thuộc rõ ràng, tương đối dễ test và phù hợp cả thread pool lẫn callback bất đồng bộ nếu lập trình viên thực sự truyền context theo tác vụ.

Ưu điểm: không phụ thuộc trạng thái ngầm của thread, dễ đọc hợp đồng. Nhược điểm: cần truyền qua nhiều lớp; không nên biến nó thành một đối tượng chứa mọi thứ hoặc kéo dữ liệu riêng tư vào nơi không cần thiết.

### 4.2. Gắn thêm thông tin có chọn lọc vào exception

Một exception domain có thể chứa error code và một vài ID cần thiết; khi chuyển lỗi qua tầng, nó vẫn cho caller biết thao tác liên quan:

~~~java
// Trích đoạn trong một lớp Java.
final class OrderWriteException extends RuntimeException {
    private final String errorCode;
    private final String orderId;

    OrderWriteException(String orderId, Throwable cause) {
        super("cannot save order", cause);
        this.errorCode = "ORDER_WRITE_FAILED";
        this.orderId = orderId;
    }

    String errorCode() {
        return errorCode;
    }

    String orderId() {
        return orderId;
    }
}
~~~

Đây là trích đoạn biên dịch được khi đặt vào một file/lớp thích hợp. Constructor `RuntimeException(String, Throwable)` giữ nguyên cause; trường typed giúp gọi chương trình phân loại mà không phải tách chuỗi message. Không đưa token, dữ liệu thanh toán hoặc payload lớn vào exception vì exception có thể lan sang log, telemetry hoặc response không kiểm soát.

### 4.3. Structured logging context / MDC

Các thư viện logging phổ biến, chẳng hạn SLF4J kết hợp backend có hỗ trợ `MDC` (Mapped Diagnostic Context), cho phép đặt các trường chung cho log trong phạm vi hiện tại. Đây là **khả năng của thư viện logging**, không phải API `MDC` có sẵn trong Java SE.

~~~java
// Minh họa cần SLF4J + logging backend thích hợp; không chạy chỉ bằng JDK.
try {
    org.slf4j.MDC.put("requestId", context.requestId());
    org.slf4j.MDC.put("operation", context.operation());
    service.execute(context);
} finally {
    org.slf4j.MDC.remove("requestId");
    org.slf4j.MDC.remove("operation");
}
~~~

MDC thường gắn với thread (tùy implementation), vì vậy phải **dọn trong finally** để tránh rò rỉ ID sang request kế tiếp được xử lý trên cùng thread pool. Trong luồng khác hoặc stage async, không nên giả định MDC tự truyền; cần capture/restore hoặc dùng cơ chế context propagation được framework hỗ trợ.

**Lựa chọn thực tế:** business/context object rõ ràng làm nguồn dữ liệu tin cậy; MDC hoặc structured logging là cách thuận tiện để xuất các trường vào nhiều dòng log ở một phạm vi đã kiểm soát.

## 5. Bọc ngoại lệ để thêm ngữ cảnh: không đánh mất cause

Một lỗi kỹ thuật có thể đi qua nhiều lớp:

~~~text
Repository: connection timeout
      ↓ cause
Application service: cannot persist order
      ↓ context
Request boundary: operation=place_order, requestId=..., orderId=...
~~~

Nếu chỉ ném:

~~~java
// Không nên làm như vậy nếu cần giữ nguyên nhân gốc.
throw new IllegalStateException("order failed");
~~~

thì tầng ngoài có thể mất khả năng thấy exception gốc, stack trace gốc và phân loại lỗi từ dependency.

Nên dùng:

~~~java
throw new IllegalStateException("order failed: " + orderId, originalCause);
~~~

Với dữ liệu nhạy cảm, thay vì ghép mọi giá trị vào message, giữ một số ID có kiểm soát trong trường typed và đưa vào structured log ở ranh giới. `Throwable.getCause()` cho phép đi ngược chuỗi lỗi, ví dụ `SQLException` → `RepositoryException` → `OrderWriteException`.

**Đừng bọc lại cùng một lỗi ở mọi tầng** mà không bổ sung ý nghĩa mới. Chuỗi năm lớp `RuntimeException("failed")` có thể làm log dài nhưng không thêm manh mối. Chỉ bọc ở ranh giới abstraction có sự chuyển đổi ngữ nghĩa, ví dụ từ lỗi JDBC sang lỗi lưu trữ đơn hàng.

### Lỗi dự kiến và lỗi bất ngờ

- Lỗi nghiệp vụ như hàng hết hoặc đơn đã đóng: một mã lỗi có cấu trúc và business ID có thể đủ; log mức WARN/INFO tùy chính sách và tần suất.
- Lỗi không dự kiến như vi phạm invariant, lỗi database hoặc coding bug: cần log mức ERROR khi tác động đủ nghiêm trọng, giữ stack trace/cause và context.
- Lỗi do timeout/cancellation: cần tách với failure thông thường; nếu task bị hủy đúng chính sách, ghi WARN/INFO có thể hợp lý hơn ERROR.
- Đừng dùng một mức log cố định chỉ dựa trên tên lớp exception, không xét tác động và kỳ vọng nghiệp vụ.

## 6. Chương trình Java 17 chạy độc lập: thêm context và giữ nguyên nhân gốc

Ví dụ này chỉ dùng Java SE, không phụ thuộc SLF4J để có thể biên dịch và chạy bằng `javac`. Ứng dụng production nên đưa các trường vào một structured logger thay vì nối tay chuỗi dài.

Lưu toàn bộ chương trình thành **`ExceptionContextDemo.java`**:

~~~java
import java.util.Objects;

public class ExceptionContextDemo {
    record OperationContext(
            String operation, String requestId, String orderId) {
        OperationContext {
            Objects.requireNonNull(operation, "operation");
            Objects.requireNonNull(requestId, "requestId");
            Objects.requireNonNull(orderId, "orderId");
        }
    }

    static final class OrderWriteException extends RuntimeException {
        private final String errorCode;
        private final String orderId;

        OrderWriteException(String orderId, Throwable cause) {
            super("could not save order", cause);
            this.errorCode = "ORDER_WRITE_FAILED";
            this.orderId = orderId;
        }

        String errorCode() {
            return errorCode;
        }

        String orderId() {
            return orderId;
        }
    }

    static void persist() {
        throw new IllegalStateException("storage unavailable");
    }

    static void placeOrder(OperationContext context) {
        try {
            persist();
        } catch (IllegalStateException cause) {
            throw new OrderWriteException(context.orderId(), cause);
        }
    }

    static void handleRequest(OperationContext context) {
        try {
            placeOrder(context);
        } catch (OrderWriteException ex) {
            System.out.printf(
                    "level=ERROR operation=%s requestId=%s orderId=%s code=%s%n",
                    context.operation(), context.requestId(),
                    ex.orderId(), ex.errorCode());

            System.out.println("exception="
                    + ex.getClass().getSimpleName());

            Throwable cause = ex.getCause();
            System.out.println("cause="
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }
    }

    public static void main(String[] args) {
        OperationContext context = new OperationContext(
                "place_order", "req-17", "ord-42");
        handleRequest(context);
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac ExceptionContextDemo.java
java ExceptionContextDemo
~~~

**Stdout chính xác:**

~~~text
level=ERROR operation=place_order requestId=req-17 orderId=ord-42 code=ORDER_WRITE_FAILED
exception=OrderWriteException
cause=IllegalStateException: storage unavailable
~~~

Tại sao ví dụ này có ích?

1. `OperationContext` lưu thông tin nhận diện thao tác ở dạng bất biến của Java record.
2. `persist()` ném lỗi kỹ thuật gốc. `placeOrder()` chuyển lỗi sang abstraction nghiệp vụ bằng `OrderWriteException` **và truyền `cause`**.
3. `handleRequest()` là ranh giới ghi nhận lỗi; nó có operation, request ID, order ID, error code, loại exception và nguyên nhân gốc.
4. Việc in ở ranh giới giúp tránh log toàn stack trace lặp lại ở từng tầng trong một request.
5. Đầu ra được tạo bằng giá trị cố định, không phụ thuộc thời gian, thread scheduler, tên máy hoặc logger implementation.

**Trong production:** ngoài những trường đang in, hãy truyền toàn bộ `Throwable` cho logging backend để giữ stack trace và chuỗi nguyên nhân. Ví dụ stdout cố ý chỉ hiển thị type/message giúp xác minh bài học với kết quả xác định, **không phải** lời khuyên bỏ stack trace khỏi log điều tra.

## 7. Structured logging có giá trị hơn ghép một chuỗi tự do

Một sự kiện log nên có các **field tách biệt** để hệ thống lưu trữ có thể filter, group, thống kê và liên kết.

Mẫu JSON minh họa (không phải output của chương trình):

~~~json
{
  "timestamp": "2026-10-19T03:00:00Z",
  "level": "ERROR",
  "service": "order-service",
  "event": "order_persist_failed",
  "operation": "place_order",
  "requestId": "req-17",
  "orderId": "ord-42",
  "errorCode": "ORDER_WRITE_FAILED",
  "dependency": "orders-db",
  "exception": {
    "type": "OrderWriteException",
    "causeType": "IllegalStateException"
  }
}
~~~

Giá trị timestamp và ID ở đây là giả định để minh họa schema, không phải dữ liệu thực. Hệ thống logging production thường tự bổ sung `timestamp`, `service`, `severity`, hostname và trace context; tránh làm mỗi team phát minh tên field khác nhau.

Lợi ích:

- Truy vấn `requestId = "req-17"` hoặc `errorCode = "ORDER_WRITE_FAILED"` đáng tin hơn tìm substring trong text.
- Nhóm lỗi theo code và operation mà không cần parse message.
- Dễ gắn với metrics/traces và dashboard.
- Hạn chế thay đổi truy vấn khi copywriting của message thay đổi.

Một log với `"order id req-17 failed"` không tốt bằng các field `orderId` và `requestId` riêng: hai ID có ngữ nghĩa khác và người điều tra không nên đoán bằng regex.

### Placeholder logging và Throwable

Nhiều framework logging có API parameterized logging, ví dụ SLF4J:

~~~java
// Minh họa: log là org.slf4j.Logger, context đã khai báo.
log.error("operation={} requestId={} orderId={} code={}",
        context.operation(), context.requestId(),
        context.orderId(), "ORDER_WRITE_FAILED", exception);
~~~

Đoạn trên **không phải code Java SE độc lập**: cần SLF4J và backend. Thứ tự tham số cuối cùng cần đúng với quy tắc API logger để backend nhận `exception` làm Throwable và ghi stack trace; trong thư viện/version khác hãy đọc chính xác overload hỗ trợ. Nếu backend hỗ trợ structured arguments/key-value pairs, ưu tiên chúng thay vì chỉ nhét giá trị vào chuỗi format.

Đừng dùng `ex.printStackTrace()` cùng với `log.error(..., ex)` một cách không kiểm soát: thường tạo bản sao stack trace trong hai kênh khác nhau.

## 8. Log một lần có trách nhiệm, không log mỗi lần catch

Một lỗi đi qua nhiều tầng có thể tạo ba bản log trùng:

~~~text
Repository: ERROR write failed
Service: ERROR order failed
Controller: ERROR request failed
~~~

Nếu cả ba đều in cùng stack trace, hệ thống có thể báo ba lỗi thay vì một và gây khó khăn khi xác định mức độ ảnh hưởng thật.

**Quy ước thực hành:**

- Tầng thấp **ném/bọc đúng ngữ nghĩa và giữ cause**.
- Tầng có quyền quyết định retry có thể log ở mức DEBUG/INFO cho mỗi attempt hoặc cập nhật metrics, tránh coi mỗi lần retry là lỗi cuối cùng.
- Tầng boundary chịu trách nhiệm phản hồi request/job/message nên log **một sự kiện failure cuối cùng đủ context** khi thực sự không phục hồi được.
- Trường hợp lỗi bị xử lý thành công bằng fallback, không nhất thiết log ERROR; nếu cần quan sát, log sự kiện recovery với mức phù hợp.
- Không áp dụng cứng “mỗi lỗi chỉ được log một lần” trong mọi kiến trúc: có thể có sự kiện riêng ở từng ranh giới quan trọng. Nhưng mỗi sự kiện phải bổ sung thông tin và mục đích mới, không nhân bản y hệt stack trace.

Người điều tra cần phân biệt một failure trải qua nhiều stage với nhiều failure độc lập. Dùng `requestId`/`traceId` và một `errorCode` ổn định hỗ trợ xác định quan hệ giữa các sự kiện.

## 9. Lựa chọn những định danh thực sự giúp điều tra

Các ID tốt cần thỏa mãn một số tiêu chí:

1. **Tìm được:** ID có thể dùng để truy vấn record/traces đúng quyền; ID ngẫu nhiên vô nghĩa và không lưu ở đâu thì ít giá trị.
2. **Ổn định theo phạm vi:** cùng một thao tác giữ ID xuyên qua các bước liên quan; retry có thể giữ business ID nhưng thay execution ID.
3. **Có tên rõ:** `orderId` không bị dùng để chứa `requestId`. Nếu một ID được sinh từ external provider, tên nên nêu namespace.
4. **Độ nhạy phù hợp:** có những ID vẫn là dữ liệu có thể liên kết tới người dùng; không phải ID nào cũng an toàn để log công khai.
5. **Độ dài và cardinality có kiểm soát:** đủ để phân biệt nhưng không biến nó thành tên metric label có cardinality cực lớn.
6. **Hợp đồng format:** nên chuẩn hóa `UUID`, ID từ tracing hoặc chuỗi theo một schema, có validation tại ranh giới.

### Request ID không thay business ID

Một request có thể cập nhật nhiều đơn; cùng một đơn cũng có thể trải qua nhiều request. Bởi vậy hai trường trả lời câu hỏi khác nhau:

~~~text
requestId=req-abc    orderId=ord-42     operation=create_order
requestId=req-def    orderId=ord-42     operation=cancel_order
~~~

Đây có thể là **hai thao tác hợp lệ khác nhau** trên cùng đơn. Nếu log chỉ có `orderId`, khó biết request nào gây lỗi; nếu chỉ có `requestId`, khó tìm toàn bộ lịch sử của đơn.

### Retry và định danh lần chạy

Khi một message được retry, hãy cân nhắc:

~~~text
messageId=msg-802 executionId=exec-1 attempt=1
messageId=msg-802 executionId=exec-2 attempt=2
~~~

ID message ổn định để gom mọi lần xử lý cùng nội dung; execution ID và attempt để phân tích một lần thất bại. Dù có `attempt=2`, không thể tự kết luận lần đầu không gây side effect: retry và idempotency phải được thiết kế riêng.

## 10. Truyền context qua CompletableFuture và thread pool

Một lỗi phổ biến là đặt request ID trong `ThreadLocal`/MDC ở thread HTTP, rồi dùng `CompletableFuture.supplyAsync(...)` trên executor khác và giả định context tự xuất hiện.

Trong thực tế, `ThreadLocal` gắn với thread cụ thể. Các task trong thread pool có thể chạy trên thread đã từng phục vụ request khác. Không tự truyền context có thể tạo log thiếu ID; không dọn MDC có thể tạo log **gắn nhầm ID khách hàng của request trước**.

Một cách độc lập framework là **truyền context như tham số bất biến**:

~~~java
// Mã minh họa trong phương thức có Executor executor,
// OperationContext context và phương thức repositorySave(context).
CompletableFuture<String> task =
        CompletableFuture.supplyAsync(() -> {
            try {
                repositorySave(context);
                return "saved";
            } catch (RuntimeException cause) {
                throw new OrderWriteException(context.orderId(), cause);
            }
        }, executor);
~~~

Đây là **trích đoạn, không phải chương trình độc lập**; các loại và biến phải được định nghĩa trong hệ thống. `context` được lambda capture có chủ đích, không phụ thuộc vào việc executor chọn thread nào.

Nếu dùng MDC:

1. Chụp những field cần thiết **ở trước ranh giới bất đồng bộ**.
2. Trong task, thiết lập MDC cho thời gian thực thi.
3. Dùng `try/finally` hoặc API scope tương ứng để restore giá trị trước đó (không chỉ clear toàn cục nếu một scope bên ngoài đang tồn tại).
4. Dọn context trên đường success, exception, cancellation.
5. Kiểm tra cách framework xử lý virtual threads, reactive chain hoặc structured context riêng của nó; không suy luận cơ chế truyền context chỉ từ tên thư viện.

### Future báo lỗi không tự mang toàn bộ context

Khi `future.get()` ném `ExecutionException` hoặc `future.join()` ném `CompletionException`, caller nhận wrapper và `cause` nhưng **không được bảo đảm nhận `ThreadLocal` của worker**. Vì vậy ID nghiệp vụ quan trọng nên được truyền rõ hoặc gắn vào exception/result có kiểm soát.

Nếu cần log thất bại tại ranh giới request, caller nên giữ `OperationContext` tương ứng với tác vụ, ví dụ map `requestId -> task` hoặc closure đi kèm future, thay vì suy đoán request ID từ tên thread.

## 11. Exception context trong các ranh giới khác

### HTTP request

Context hữu ích: `method`, route template, server-generated `requestId`, `operation`, authenticated subject ID đã được chuẩn hóa và được phép log, mã lỗi ứng dụng, latency, mã HTTP trả về. Không log nguyên auth header, cookie, token hoặc body tùy tiện.

Một ranh giới web có thể:

- Tạo hoặc xác minh correlation ID.
- Truyền ID xuống service/repository.
- Bắt lỗi ở boundary, map sang status/errorCode công khai.
- Log stack/cause trong kênh nội bộ, trả về response an toàn và `requestId` để hỗ trợ người dùng cung cấp cho support.

### Queue và event

Context hữu ích: `messageId`, `topic`, `partition`/`offset` (khi có), `consumerGroup`, `attempt`, business ID. Với retry, giữ một correlation ID xuyên suốt nhưng phân biệt execution attempt. Không bao giờ log toàn bộ payload nhạy cảm chỉ vì deserialization lỗi.

### Batch/cron job

Context hữu ích: `jobName`, `jobRunId`, `batchId`, `recordId`, `step` và số thứ tự nếu cần. Nếu một record trong batch lỗi, log bằng `recordId` (hợp lệ và an toàn) giúp truy tìm bản ghi cụ thể; `jobRunId` giúp tổng hợp một đợt chạy.

### Database và các dịch vụ ngoài

Context hữu ích: tên dependency ổn định, loại operation, server-side request ID của provider (nếu cho phép), retry attempt, elapsed time và mã lỗi chuẩn. Hạn chế ghi SQL đầy đủ có dữ liệu nội tuyến; dùng query name/template hoặc operation code. Không in connection string chứa password.

## 12. Bảo vệ dữ liệu nhạy cảm và chống log injection

Context hữu ích không đồng nghĩa **càng nhiều càng tốt**. Log được sao chép sang nhiều hệ thống lưu trữ, truy vấn và cảnh báo; nó có thể được xem bởi nhiều người hơn hệ thống nghiệp vụ nguồn.

**Không ghi vào log nếu không có cơ sở nghiệp vụ, quyền và biện pháp bảo vệ phù hợp:**

- Mật khẩu, API key, access token, refresh token, session cookie.
- Dữ liệu thẻ thanh toán đầy đủ, mã xác minh thẻ, bí mật xác thực.
- Nội dung giao dịch hoặc thông tin sức khỏe, địa chỉ, email, số điện thoại khi không thực sự cần.
- Raw request/response chứa thông tin cá nhân hoặc bí mật.
- Toàn bộ header, URL query string hoặc nội dung exception từ dịch vụ ngoài khi có thể chứa token.

Các biện pháp:

1. **Allowlist field:** quyết định trước trường nào được log, thay vì log toàn bộ object, `toString()` hoặc HTTP payload.
2. **Redaction:** che giá trị nhạy cảm trước khi chuyển cho logger; chú ý cả message và cause từ thư viện bên ngoài.
3. **Validation & encoding:** giới hạn chiều dài, kiểm tra ký tự ID do client cung cấp; xử lý newline/control characters để giảm nguy cơ chèn dòng log giả.
4. **Retention & access control:** xác định nơi lưu log, thời hạn lưu, quyền xem và đường xuất dữ liệu.
5. **Hash/pseudonymize khi thích hợp:** nếu cần liên kết sự kiện mà không hiện định danh nguyên bản, dùng cách biến đổi được bảo vệ phù hợp với chính sách; không mặc định hash thông thường biến thông tin thành vô danh.
6. **Kiểm thử:** đưa vào input chứa newline, control chars, chuỗi dài và nội dung nhạy cảm giả định để kiểm tra sự kiện log vẫn an toàn.

**Lưu ý:** ngay cả một `userId` hoặc `orderId` hợp lệ có thể trở thành dữ liệu liên kết cá nhân khi ghép với hệ thống khác. Đừng đánh đồng “không có tên người” với “không nhạy cảm”.

## 13. Phân biệt message, error code và ID

Một lỗi hữu ích thường có ba lớp thông tin khác nhau:

- **Exception message:** mô tả ngắn tình huống, có thể thay đổi để dễ hiểu hơn. Không dùng text message làm API machine-readable.
- **Error code:** mã ổn định mà hệ thống dùng để phân loại, ví dụ `ORDER_WRITE_FAILED` hoặc `INVENTORY_NOT_AVAILABLE`. Có thể tài liệu hóa cho caller hoặc người vận hành.
- **Identifiers:** request/business/job IDs để tìm sự kiện và dữ liệu liên quan.

Ví dụ:

~~~text
message=could not save order
errorCode=ORDER_WRITE_FAILED
requestId=req-17
orderId=ord-42
~~~

Nếu đổi message thành `order persistence failed`, truy vấn theo `errorCode` vẫn có thể giữ nguyên. Nếu mỗi exception tạo mã ngẫu nhiên thay cho error code ổn định, hệ thống không thể tổng hợp lỗi cùng loại.

Một ID điều tra như `incidentId` có thể giúp support tìm lỗi cụ thể; nhưng nếu không có ánh xạ tới log hoặc trace thực, việc hiển thị incident ID cho người dùng cũng chưa giải quyết được vấn đề.

## 14. Mức log và thời điểm ghi context

**Mức log** nên phản ánh tính kỳ vọng và tác động, không chỉ việc có exception.

| Tình huống | Mức thường cân nhắc | Context ưu tiên |
|---|---|---|
| Input không hợp lệ được API trả 400 bình thường | INFO/WARN hoặc không log từng yêu cầu nếu đã có metrics | route/operation, requestId, errorCode |
| Trùng message nhưng idempotency xử lý được | INFO/DEBUG | messageId, operation, attempt |
| Retry tạm thời do dependency quá tải | WARN/DEBUG cho attempt, ERROR cho failure cuối | dependency, retry count, correlationId |
| Lỗi lưu dữ liệu chưa thể phục hồi | ERROR | operation, businessId, requestId, cause |
| Cancellation có chủ đích | DEBUG/INFO tùy hệ thống | taskId, cancel reason đã chuẩn hóa |
| Vi phạm invariant hoặc lỗi bất ngờ | ERROR | operation, IDs, stack/cause, version |
| Quá hạn/hết thời gian chờ | WARN/ERROR theo tác động | dependency, elapsedMs, timeout policy, attempt |

Tránh log lỗi đầu vào bình thường ở mức ERROR cho mọi request: một đợt traffic không hợp lệ có thể khiến alert bị nhiễu và log volume cao. Ngược lại, không được giảm mức log của lỗi có nguy cơ mất dữ liệu chỉ vì nó được biểu diễn bằng unchecked exception.

### Tỷ lệ log và cardinality

Các ID có cardinality cao như `requestId` và `orderId` rất hữu ích trong **log/traces** để truy vấn một lần thực thi. Tuy nhiên, không nên dùng chúng làm label dimensions mặc định cho metrics vì tạo vô số time series. Metric tốt có thể nhóm theo `operation`, `errorCode` và `dependency`; khi cần điều tra một sự kiện cá biệt, tra từ metric sang log/tracing có ID chi tiết.

## 15. Bảo toàn ngữ cảnh khi retry, timeout và cancellation

Một lỗi có thể được retry:

~~~text
operation=save_order orderId=ord-42 attempt=1 outcome=retry
operation=save_order orderId=ord-42 attempt=2 outcome=success
~~~

Kết quả cuối là thành công, nhưng attempt đầu vẫn thất bại. Không đếm attempt failure là request failure cuối cùng nếu người dùng không bị ảnh hưởng. Một cảnh báo cuối nên ghi tổng số lần thử và nguyên nhân cuối nếu tất cả retry hết.

Với timeout:

- `TimeoutException` cho biết một giới hạn chờ bị vượt; nó **không chứng minh** thao tác ở dependency đã dừng hoặc chưa commit.
- Cần giữ `requestId`, `operation`, tên dependency, `elapsedMs` và các ID của request gửi sang provider nếu có.
- Nếu caller retry sau timeout, dùng idempotency key hoặc cơ chế điều tra trạng thái theo domain để tránh ghi trùng side effect.

Với cancellation/interruption:

- `CancellationException` và `InterruptedException` nên được phân biệt với lỗi nghiệp vụ.
- Nếu catch `InterruptedException` mà không thể truyền tiếp, thường cần `Thread.currentThread().interrupt()`, đồng thời ghi nhận ID tác vụ và kết thúc theo chính sách hủy.
- Đừng log ERROR một tác vụ bị hủy có chủ đích chỉ vì nó phát sinh exception; nhưng nếu hủy để lại dữ liệu sai, đó là một failure khác cần điều tra.

## 16. Điều tra từ một error event như thế nào?

Khi một sự kiện failure đủ context được ghi, quy trình thực hành có thể là:

1. **Khoanh vùng một sự kiện:** tìm theo `requestId`, `jobRunId` hoặc ID mà người dùng/support cung cấp.
2. **Xác định operation/stage:** xem hệ thống đang làm bước nào, dependency nào được gọi, có bao nhiêu retry/attempt.
3. **Đọc chuỗi exception:** phân biệt exception ở ranh giới ứng dụng với cause kỹ thuật, xem stack trace và suppressed exceptions khi có.
4. **Đối chiếu trace:** dùng `traceId` để xem luồng xuyên dịch vụ, tìm span có lỗi hoặc độ trễ bất thường.
5. **Kiểm tra business state:** dùng `orderId`/`jobId` theo cơ chế truy vấn có quyền để xác định dữ liệu đã commit hay chưa.
6. **Xem tính lặp lại:** group theo errorCode, operation, release/version, dependency và thời gian.
7. **Xác định hành động:** retry có an toàn không, cần compensation không, có ảnh hưởng nhiều khách hàng không.
8. **Ghi nhận kết luận:** phát hiện nguyên nhân gốc, chính sách sửa, test hồi quy và điều chỉnh thông tin log cần thiết.

**Một log chưa đủ để khẳng định nguyên nhân cuối cùng** chỉ vì chứa tên một dependency. Một `SQLException` có thể do cấu hình, network, pool hết kết nối hoặc DB quá tải. Context giúp đặt đúng câu hỏi; cần đối chiếu bằng chứng từ metrics/traces và trạng thái thực.

## 17. Các sai lầm phổ biến

1. **Chỉ log `ex.getMessage()`:** mất stack, cause và ngữ cảnh thao tác.
2. **Chỉ log stack trace:** thấy method lỗi nhưng không biết request hoặc đối tượng nghiệp vụ nào.
3. **Tự sinh request ID mới ở mỗi tầng:** làm đứt liên kết chuỗi sự kiện.
4. **Dùng một field chung `id`:** không biết đó là request, order hay message.
5. **Bọc exception rồi bỏ cause:** xóa dấu vết kỹ thuật gốc.
6. **Log y hệt cùng một exception ở mọi catch:** nhân bản sự kiện, tăng volume và dễ tạo alert trùng.
7. **Truyền toàn bộ DTO/object vào logger:** vô tình ghi dữ liệu nhạy cảm; `toString()` có thể đổi và gây rò rỉ.
8. **Dùng MDC nhưng không cleanup:** request tiếp theo trên cùng thread pool có thể bị gắn nhầm ID.
9. **Cho rằng context trong ThreadLocal tự xuyên qua CompletableFuture:** thiếu hoặc sai context khi đổi thread.
10. **Dùng ID khách hàng làm metric label:** cardinality quá cao.
11. **Coi error message là error code ổn định:** việc đổi câu chữ làm hỏng dashboard và phân loại lỗi.
12. **Trả stack trace nguyên vẹn cho HTTP client:** lộ thông tin triển khai, đường dẫn nội bộ hoặc bí mật; nên trả error code và request ID an toàn.
13. **Tin ID đến từ header mà không validation:** nguy cơ chuỗi quá dài, ký tự điều khiển hoặc log injection.
14. **Log toàn bộ URL/header/token trong tình huống lỗi:** tăng rủi ro bảo mật dữ liệu.
15. **Gắn `orderId` vào lỗi chưa xác định được order:** tạo ngữ cảnh sai; dùng null/omit field có tài liệu thay vì bịa ID.
16. **Hiểu timeout/cancel là chưa commit:** cần xác minh trạng thái nghiệp vụ chứ không dựa vào loại exception.

## 18. Cách kiểm thử khả năng điều tra của exception log

Một bộ test log nên kiểm tra **trường dữ liệu** thay vì so khớp nguyên chuỗi log có timestamp động:

| Kịch bản | Kiểm tra |
|---|---|
| Lỗi kỹ thuật được bọc bằng exception miền nghiệp vụ | `cause` không null và đúng loại; `errorCode` ổn định |
| Request thất bại ở service | Sự kiện có operation, requestId và business ID hợp lệ |
| Gọi API với ID thiếu hoặc quá dài | Validation/fallback ID hoạt động, không phá format log |
| Input chứa newline/control characters | Không thể làm giả một dòng/sự kiện log mới |
| Logging qua thread pool | Context không bị lẫn giữa hai task |
| Tác vụ CompletableFuture thất bại | Stage/boundary giữ đúng context và cause |
| Retry nhiều lần rồi thành công | Phân biệt attempt errors và outcome cuối |
| Timeout/hủy task | Có trạng thái phù hợp; không log sai “đã rollback” |
| Dữ liệu nhạy cảm trong exception từ dependency | Logger/redaction không để lộ secret ở message/cause |
| Failure gây nhiều tầng exception | Không tạo vô số bản log ERROR trùng cùng một nguyên nhân |

Đối với structured logger, nên dùng test appender hoặc collector thử nghiệm có khả năng đọc từng field và Throwable. Với chương trình Java SE đơn giản, có thể capture `System.out` để kiểm tra ví dụ, nhưng production không nên thay thế công cụ logging bằng print statement.

Một test tốt cho log context cần có **hai request khác nhau trên cùng executor một luồng**: mỗi task giữ đúng request ID, task sau không nhìn thấy ID task trước. Đây là cách phát hiện MDC leak mà test một request không nhìn thấy.

## 19. Checklist thiết kế logging cho một thao tác Java

Trước khi hoàn thành một API hoặc tác vụ nền, rà soát:

- **Tên operation:** ổn định, không mơ hồ và đúng ranh giới nghiệp vụ.
- **Correlation:** request/correlation/trace ID được tạo hoặc xác minh tại ingress rồi truyền nhất quán.
- **Business identity:** chỉ những ID thực sự giúp tra cứu, không nhồi toàn bộ payload.
- **Error classification:** có `errorCode` đủ ổn định, phân biệt failure cuối, retry, timeout và cancel.
- **Root cause:** exception được bọc bằng constructor có `cause`; log truyền Throwable cho backend.
- **Logging boundary:** tránh nhiều lớp cùng in một stack trace mà không thêm ý nghĩa.
- **Async propagation:** context được capture và truyền đúng qua executor/future; MDC được restore/cleanup.
- **Data minimization:** không log token, bí mật hoặc PII ngoài phạm vi cho phép; ID đầu vào được validate.
- **Diagnostic usefulness:** từ một dòng log có thể tìm request/trace và trạng thái đối tượng liên quan.
- **Verification:** test thành phần log, race/retry, input bất thường và trường hợp nhạy cảm.

## 20. Ghi nhớ cốt lõi

**Thêm ngữ cảnh thao tác và định danh có ích cho điều tra** là tạo đủ dấu vết để biến một exception riêng lẻ thành một sự kiện có thể tìm kiếm, liên kết và giải thích. Tối thiểu thường gồm **operation**, **request/correlation ID**, **business ID nếu có**, **error code** và **Throwable/cause** được giữ nguyên. Với tác vụ bất đồng bộ, cần truyền context qua ranh giới thread một cách có chủ đích.

Giá trị của log không được đo bằng số trường tối đa, mà bằng khả năng trả lời **đúng việc gì thất bại, ở đâu, cho đối tượng nào, do nguyên nhân nào và trạng thái hiện tại là gì**, trong khi vẫn giữ bảo mật, giới hạn cardinality và tránh thông tin sai lệch.

### Tham khảo

- [Java SE 17 — Throwable, cause và suppressed exceptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)
- [Java SE 17 — RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html)
- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html)
- [SLF4J Manual — MDC and parameterized logging](https://www.slf4j.org/manual.html)
- [OpenTelemetry — Trace and span concepts](https://opentelemetry.io/docs/concepts/signals/traces/)
