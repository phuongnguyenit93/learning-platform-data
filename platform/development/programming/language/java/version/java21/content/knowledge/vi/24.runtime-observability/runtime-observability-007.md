# Tương quan request ID, trace ID và tên task thay vì phụ thuộc carrier

Trong ứng dụng Java 21, đặc biệt khi dùng virtual threads, không nên dùng carrier thread làm định danh chính để nối các log thuộc cùng một request. Một virtual thread có thể được mount và unmount trên các carrier khác nhau trong suốt vòng đời; carrier là chi tiết lập lịch của JVM, không phải danh tính của request hoặc task nghiệp vụ.

Hãy ghi các định danh có ý nghĩa ở cấp ứng dụng như `requestId`, `traceId`, `spanId` và `taskName` trong log, trace và context của công việc. Tên thread, thread ID và trạng thái virtual/platform vẫn hữu ích cho chẩn đoán, nhưng chỉ nên là metadata bổ sung. Cách làm này cũng hữu ích với platform thread pool, nơi một worker thread có thể xử lý nhiều request khác nhau theo thời gian.

## 1. Phân biệt các định danh

Các trường sau giải quyết các câu hỏi khác nhau:

| Trường | Phạm vi và mục đích | Có nên dùng làm correlation chính? |
| --- | --- | --- |
| `requestId` | Định danh một request hoặc một đơn vị nghiệp vụ trong phạm vi hệ thống. Có thể được tạo ở ingress hoặc nhận từ gateway sau khi xác thực/kiểm tra. | Có, để tìm log của cùng request. |
| `traceId` | Định danh toàn bộ distributed trace, có thể đi qua nhiều service và nhiều process. | Có, để liên kết các span trong cùng một luồng xử lý phân tán. |
| `spanId` | Định danh một operation/span cụ thể bên trong trace; span con có parent span ID. | Có, để xác định operation đang phát sinh log. |
| `taskName` | Tên nghiệp vụ hoặc bước thực thi, ví dụ `load-customer`, `authorize-payment`, `write-response`. | Có, để hiểu log thuộc bước nào; không thay thế ID duy nhất. |
| `threadName` | Tên thread JVM, thường hữu ích khi xem log hoặc thread dump. | Chỉ bổ sung để chẩn đoán. |
| `threadId` | ID của đối tượng `Thread` trong JVM. | Chỉ bổ sung; không đại diện request hoặc trace. |
| Carrier thread | Platform thread tạm thời thực thi virtual thread. | Không dùng làm định danh request/task. |

Một request có thể tạo nhiều task và span. Nhiều request cũng có thể lần lượt chạy trên cùng một platform worker. Một trace có thể đi qua nhiều service, mỗi service có request ID nội bộ khác nhau. Vì vậy, không đồng nhất các trường này với nhau.

## 2. Vì sao carrier không phải định danh ổn định?

Virtual thread là thread do JVM quản lý. Khi virtual thread thực hiện thao tác blocking tương thích, JVM có thể unmount nó khỏi carrier để carrier xử lý công việc khác. Khi virtual thread tiếp tục chạy, JVM có thể mount nó lên một carrier khác.

```text
Request R-42 / Virtual thread V-17
       |
       +-- xử lý bước A trên carrier C-3
       |
       +-- blocking I/O: virtual thread unmount
       |
       +-- tiếp tục bước B trên carrier C-8
       |
       +-- xử lý bước C trên carrier C-3 hoặc carrier khác
```

Đây là sơ đồ khái niệm; việc chọn carrier do JVM quyết định. Cùng một request và virtual thread có thể xuất hiện trên các carrier khác nhau. Ngược lại, một carrier có thể lần lượt thực thi nhiều virtual thread.

Nếu log chỉ ghi tên hoặc ID của carrier, các dòng của cùng một request có thể bị tách thành nhiều nhóm, còn các request khác nhau có thể bị trộn vào cùng nhóm carrier. Dùng `requestId`/`traceId` để tương quan; ghi `threadName`, `threadId` và `Thread.currentThread().isVirtual()` như thông tin chẩn đoán phụ.

## 3. Tạo context có định danh ở cấp ứng dụng

Một cách đơn giản là gom context cần thiết vào một kiểu dữ liệu bất biến rồi truyền theo các lời gọi và task:

```java
record CorrelationContext(
        String requestId,
        String traceId,
        String spanId,
        String taskName
) {
    CorrelationContext forTask(String nextTaskName, String nextSpanId) {
        return new CorrelationContext(
                requestId,
                traceId,
                nextSpanId,
                nextTaskName
        );
    }
}
```

`requestId` được giữ nguyên trong phạm vi request. `traceId` được giữ nguyên trong cùng trace. Khi bắt đầu một operation/span con, hệ thống tracing tạo `spanId` mới và context của task được cập nhật tương ứng. `taskName` mô tả operation đang thực hiện.

Không tự tạo `spanId` mới chỉ bằng một chuỗi tùy ý nếu đang dùng OpenTelemetry hoặc một tracing SDK. Hãy để tracing SDK quản lý quan hệ parent-child, sampling và propagation; record trên minh họa cấu trúc context có thể được ghi vào log.

## 4. Ghi log với correlation fields và metadata thread

Trong Java 21 có thể dùng `System.Logger` để minh họa cách ghi các trường context cùng metadata thread. Ứng dụng production thường dùng logging framework hỗ trợ structured logging để lưu chúng thành các field riêng thay vì ghép thành một chuỗi khó truy vấn.

```java
public final class CorrelatedLogging {
    private static final System.Logger LOGGER =
            System.getLogger(CorrelatedLogging.class.getName());

    private CorrelatedLogging() {}

    static void info(CorrelationContext context, String message) {
        Thread thread = Thread.currentThread();

        LOGGER.log(
                System.Logger.Level.INFO,
                "requestId={0} traceId={1} spanId={2} task={3} "
                        + "threadName={4} threadId={5} virtual={6} message={7}",
                context.requestId(),
                context.traceId(),
                context.spanId(),
                context.taskName(),
                thread.getName(),
                thread.threadId(),
                thread.isVirtual(),
                message
        );
    }
}
```

Ví dụ output:

```text
INFO requestId=req-42 traceId=4bf92f3577b34da6a3ce929d0e0e4736 \
spanId=00f067aa0ba902b7 task=load-customer \
threadName=request-vt-17 threadId=91 virtual=true message=customer loaded
```

Trong Java 21, `Thread.threadId()` là API hiện hành để lấy ID thread; `Thread.getId()` đã deprecated. `Thread.isVirtual()` cho biết thread hiện tại có phải virtual thread hay không. Hai giá trị này hữu ích để phân tích runtime nhưng không nên dùng thay cho request ID hoặc trace ID.

## 5. Đặt tên task và virtual thread

Tên task nên mô tả công việc nghiệp vụ hoặc operation kỹ thuật ổn định, ví dụ:

- `validate-order`
- `load-customer`
- `authorize-payment`
- `publish-event`
- `write-http-response`

Tránh đặt task name theo nội dung tùy ý do người dùng gửi. Tên task không nên chứa email, token, số tài khoản hoặc dữ liệu cá nhân. Nếu có nhiều loại task, dùng một tập tên có kiểm soát để log và metric có thể phân tích được.

Java 21 cho phép đặt tên virtual thread bằng `Thread.Builder`:

```java
Thread.ofVirtual()
        .name("load-customer")
        .start(() -> loadCustomer());
```

Với executor tạo một virtual thread cho mỗi task, có thể dùng thread factory đặt prefix và số thứ tự:

```java
import java.util.concurrent.Executors;

try (var executor = Executors.newThreadPerTaskExecutor(
        Thread.ofVirtual().name("request-vt-", 0).factory()
)) {
    executor.submit(() -> handleRequest());
}
```

Prefix giúp nhận diện loại thread trong thread dump. Tuy nhiên, `request-vt-17` vẫn chỉ là tên thread runtime, không phải request ID; context của request vẫn nên được ghi riêng. Nếu một virtual thread thực hiện nhiều bước, hãy ghi `taskName` theo từng operation thay vì đổi tên thread liên tục.

## 6. Truyền context tường minh qua task

Truyền context qua tham số là cách dễ kiểm tra nhất vì ranh giới dữ liệu được thể hiện trong chữ ký phương thức. Nó không phụ thuộc task chạy trên platform thread, virtual thread hay carrier nào.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ContextPropagationExample {
    public static void main(String[] args) throws Exception {
        CorrelationContext requestContext = new CorrelationContext(
                "req-42",
                "4bf92f3577b34da6a3ce929d0e0e4736",
                "00f067aa0ba902b7",
                "handle-request"
        );

        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<?> future = executor.submit(() -> {
                CorrelationContext taskContext = requestContext.forTask(
                        "load-customer",
                        "b9c7c989f97918e1"
                );

                CorrelatedLogging.info(taskContext, "loading customer");
                loadCustomer(taskContext);
            });

            future.get();
        }
    }

    private static void loadCustomer(CorrelationContext context) {
        CorrelatedLogging.info(context, "customer lookup started");
    }
}
```

ID trong ví dụ chỉ là dữ liệu minh họa. Trong ứng dụng tracing thật, `traceId` và `spanId` phải được lấy từ tracing context đang hoạt động, không hard-code hoặc tự tăng chuỗi trong code nghiệp vụ.

Nếu dùng `CompletableFuture`, executor callback có thể là một thread khác. Hãy capture context trước khi tạo callback và truyền nó vào callback, hoặc dùng instrumentation/context-propagation library đã tích hợp với framework. Không giả định lambda tự mang theo mọi ThreadLocal của thread đã tạo nó.

## 7. ThreadLocal, MDC và context propagation

Nhiều logging framework cung cấp MDC (Mapped Diagnostic Context) để thêm `requestId`, `traceId` hoặc `spanId` vào log mà không phải truyền từng trường vào mọi lệnh log. Nhiều triển khai MDC dựa trên ThreadLocal. Điều này có một số hệ quả:

- Với virtual thread, ThreadLocal gắn với virtual thread, không phải carrier. Khi virtual thread unmount và mount sang carrier khác, context thuộc virtual thread vẫn đi cùng virtual thread.
- Khi task được chuyển sang một thread khác, chẳng hạn callback của executor hoặc `CompletableFuture`, MDC không tự động được sao chép trong mọi trường hợp.
- Với platform thread pool, nếu đặt MDC nhưng không xóa trong `finally`, request tiếp theo có thể nhìn thấy dữ liệu cũ trên worker được tái sử dụng.
- Một số framework hoặc instrumentation cung cấp cơ chế capture/restore context; hành vi phụ thuộc thư viện và cấu hình, không phải bảo đảm chung của Java SE.

Ví dụ về quy tắc cleanup khi dùng MDC của một logging framework:

```java
// Ví dụ khái niệm với MDC của logging framework.
MDC.put("requestId", context.requestId());
MDC.put("traceId", context.traceId());
try {
    handleRequest();
} finally {
    MDC.remove("requestId");
    MDC.remove("traceId");
}
```

`MDC` không thuộc Java SE 21; ví dụ trên chỉ áp dụng nếu ứng dụng dùng logging framework có API MDC tương ứng. Với task chạy qua executor, hãy dùng wrapper capture/restore của framework hoặc truyền context tường minh. Không dùng `InheritableThreadLocal` như giải pháp tổng quát cho thread pool: giá trị được kế thừa khi tạo thread, không phải mỗi lần submit task vào một worker đã tồn tại.

## 8. Trace ID, span ID và W3C Trace Context

Trong distributed tracing, `traceId` định danh toàn bộ trace; `spanId` định danh một span trong trace. Khi một service gọi service khác, span client của service gọi trở thành parent của span server ở service nhận. Các span thường chia sẻ trace ID nhưng có span ID riêng.

W3C Trace Context định nghĩa header `traceparent` với cấu trúc tổng quát:

```text
version-trace-id-parent-id-trace-flags
```

Ví dụ:

```text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

Trong ví dụ, trace ID có 32 ký tự hex, parent ID có 16 ký tự hex và flags có 2 ký tự hex. Khi tạo outbound request, tracing instrumentation tạo span client và inject `traceparent` với parent ID phù hợp. Không sao chép nguyên header inbound sang outbound nếu điều đó làm mất quan hệ parent-child của span.

Java `HttpClient` không tự động triển khai distributed tracing hoặc tự tạo `traceparent` chỉ vì request có URI. Có thể dùng OpenTelemetry Java agent/instrumentation hoặc thư viện tương thích để tạo span và inject/extract context. Nếu tự triển khai propagation, phải tuân thủ W3C Trace Context và xác thực cú pháp; không nối chuỗi header tùy tiện.

`requestId` và `traceId` có thể cùng xuất hiện trong log nhưng không nhất thiết có cùng giá trị:

- `requestId` thường phục vụ tra cứu request ở một ứng dụng hoặc gateway.
- `traceId` liên kết các operation phân tán, có thể bao gồm nhiều request nội bộ và retry.
- `spanId` giúp xác định operation cụ thể đang phát sinh log.

## 9. Không dùng request ID hoặc trace ID làm metric label có cardinality cao

Correlation ID rất hữu ích trong log và trace, nhưng thường không phù hợp làm label/tag của metric. Mỗi request có thể tạo một request ID và trace ID mới; nếu đưa chúng vào label của counter hoặc histogram, số lượng time series có thể tăng gần theo số request, gây tốn bộ nhớ và làm hệ thống metrics quá tải.

Với metrics, ưu tiên dimension có tập giá trị hữu hạn hoặc được giới hạn, ví dụ:

- HTTP method: `GET`, `POST`, `PUT`.
- Route template: `/orders/{id}` thay vì URL có ID thật.
- Operation: `authorize-payment`, `load-customer`.
- Status class: `2xx`, `4xx`, `5xx`.
- Service name và deployment environment.

Giữ `requestId`, `traceId`, `spanId` trong log/trace để tra cứu chi tiết; dùng metric label có cardinality kiểm soát để theo dõi xu hướng và SLO.

## 10. An toàn khi ghi và nhận correlation fields

Correlation fields có thể đến từ request header hoặc hệ thống bên ngoài. Không nên ghi trực tiếp mọi giá trị không tin cậy vào log:

- Giới hạn độ dài và định dạng `requestId`; từ chối hoặc thay thế giá trị chứa ký tự điều khiển như CR/LF.
- Không dùng token, session ID, email, số điện thoại hoặc dữ liệu cá nhân làm correlation ID.
- Không ghi access token, cookie, authorization header hoặc nội dung nhạy cảm vào baggage/log.
- Nếu gateway gửi request ID, quyết định rõ tin cậy gateway nào và có cần tạo ID nội bộ mới hay không.
- Với `traceparent`, dùng parser/instrumentation tuân thủ W3C thay vì tự tin mọi chuỗi header đều hợp lệ.
- Không cho phép client tùy ý tạo task name hoặc span name có cardinality không giới hạn.

Trace ID không phải bí mật xác thực. Biết trace ID không cấp quyền truy cập request; vẫn cần kiểm soát quyền truy cập log và trace backend theo chính sách bảo mật.

## 11. Quy trình tương quan khi điều tra một request

1. Bắt đầu từ request ID hoặc trace ID ở log ingress.
2. Tìm tất cả log có cùng `requestId`; dùng `traceId` để đi qua service và process khác.
3. Nhóm các log theo `spanId` để xác định operation cụ thể.
4. Đọc `taskName` để biết bước nghiệp vụ đang thực hiện.
5. Chỉ sau đó mới dùng `threadName`, `threadId` và cờ `virtual=true` để xem task đang chạy trên loại thread nào.
6. Nếu cần xem scheduler/carrier hoặc trạng thái mount/unmount, dùng công cụ chẩn đoán JVM phù hợp; không suy ra quan hệ request chỉ từ tên carrier.
7. Với lỗi qua executor boundary, kiểm tra context propagation/capture-restore và cleanup MDC ở cả task thành công lẫn task thất bại.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Các log của cùng request xuất hiện dưới nhiều carrier thread | Virtual thread có thể được mount lên carrier khác nhau. | Tương quan bằng `requestId`/`traceId`; giữ carrier chỉ là metadata chẩn đoán. |
| Nhiều request khác nhau có cùng thread name | Thread pool tái sử dụng worker cho nhiều task. | Ghi request ID và task name trong từng log event. |
| Log trong callback thiếu trace ID | Callback chạy trên thread khác và context không được capture/propagate. | Truyền context tường minh hoặc dùng instrumentation hỗ trợ context propagation. |
| Request sau nhận MDC của request trước | Worker thread được tái sử dụng nhưng MDC không được xóa. | Capture/restore MDC và cleanup trong `finally`. |
| Dùng thread ID làm request ID | Thread có thể xử lý nhiều request; request có thể đi qua nhiều thread. | Tạo request ID ở ingress và giữ nó qua các task. |
| Dùng một trace ID cho mọi span nhưng không có span ID riêng | Không thể phân biệt các operation trong cùng trace. | Tạo span riêng cho từng operation bằng tracing SDK. |
| Dùng request ID làm metric label | Cardinality tăng theo số request. | Đưa ID vào log/trace, giữ metric dimensions có giới hạn. |
| Copy nguyên `traceparent` inbound sang outbound | Parent-child relationship có thể sai vì outbound cần client span mới. | Dùng tracing instrumentation để tạo span và inject header đúng cách. |

## 13. Checklist thiết kế

1. Sinh hoặc xác thực `requestId` tại ranh giới ingress.
2. Dùng tracing SDK để quản lý `traceId`, `spanId`, parent-child và W3C propagation.
3. Ghi `taskName` theo operation nghiệp vụ ổn định.
4. Truyền correlation context qua tham số hoặc cơ chế context propagation đã được hỗ trợ.
5. Ghi thread name, thread ID và `isVirtual()` như metadata chẩn đoán, không làm khóa liên kết chính.
6. Nếu dùng MDC/ThreadLocal, capture/restore qua executor boundary và cleanup trong `finally`.
7. Giữ request/trace IDs trong log và trace; tránh đưa chúng vào metric labels có cardinality cao.
8. Kiểm tra log injection, dữ liệu cá nhân và thông tin xác thực trước khi ghi log.
9. Kiểm thử cả platform thread pool lẫn virtual threads nếu ứng dụng hỗ trợ cả hai mô hình.

## 14. Tài liệu tham khảo chính thức

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): mô hình virtual thread, mount/unmount, carrier threads và ThreadLocal.
- [Java SE 21 API — `Thread`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `threadId()`, `getName()`, `isVirtual()` và virtual-thread builders.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): định dạng `traceparent`, `tracestate` và propagation giữa các hệ thống.
- [OpenTelemetry Context](https://opentelemetry.io/docs/specs/otel/context/): context propagation và quan hệ giữa context với tracing.
- [OpenTelemetry Java Instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/): tự động tạo span và propagation cho các thư viện được hỗ trợ.
- [Java SE 21 API — `System.Logger`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.Logger.html): logging API chuẩn của Java.
