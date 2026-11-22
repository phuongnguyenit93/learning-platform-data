# Log message không ngữ cảnh: Anti-pattern logging trong ứng dụng Java

## 1. Log message không ngữ cảnh là gì?

**Log message không ngữ cảnh** (context-free hoặc context-poor logging) là anti-pattern khi một bản ghi chỉ chứa nhận xét chung chung như `Done`, `Failed`, `Updated`, `Something went wrong` hoặc một giá trị rời rạc mà **không đủ thông tin để xác định thao tác, đối tượng, kết quả và chuỗi xử lý liên quan**.

Ví dụ:

```text
INFO Done
INFO Updated
ERROR Failed
```

Trong một ứng dụng Java có hàng trăm request đồng thời, nhiều instance hoặc nhiều message consumer, ba dòng trên gần như không giúp trả lời:

- **Thao tác nào** đã thực hiện: tạo đơn hàng, cập nhật profile, thu hồi quyền, xuất báo cáo?
- **Đối tượng nào** bị tác động: order ID, job ID, resource ID, message ID?
- **Request/message/operation nào** tạo bản ghi đó?
- **Kết quả thực tế** là hoàn tất, bị từ chối, thất bại, đang retry hay chỉ vừa được tiếp nhận?
- **Thành phần nào** ghi log: service, module, method, deployment, instance?
- **Khi nào và trong bao lâu** sự việc xảy ra?
- **Tại sao thất bại**, có mã lỗi, exception hoặc quan hệ nhân quả không?

Một thông điệp ngắn không tự động là anti-pattern. `Application started` ở startup log đã có timestamp, logger, service và phiên bản trong envelope phù hợp vẫn có thể đủ. Vấn đề xuất hiện khi **thông tin cần cho mục đích điều tra hoặc vận hành bị thiếu và không thể suy ra đáng tin** từ các trường khác.

**Mục tiêu:** ghi vừa đủ context để event **tự có nghĩa**, dễ tìm kiếm và tương quan, nhưng không biến mỗi log thành bản sao request payload, session, token hoặc dữ liệu cá nhân.

## 2. Vì sao thiếu context gây khó xử lý sự cố?

Giả sử hệ thống xử lý đơn hàng:

```text
09:00:00.100 INFO Updated
09:00:00.104 ERROR Failed
09:00:00.107 INFO Retry
09:00:00.110 INFO Done
```

Không có `orderId`, `requestId`, `operation` và `outcome`, không thể biết liệu `Failed` thuộc cùng order với `Done` hay không. Một event có thể đến từ worker khác hoặc instance khác. Khoảng cách timestamp không chứng minh tính nhân quả.

Tác động thường gặp:

1. **Mean time to resolution (MTTR) tăng:** kỹ sư phải tìm thêm stack trace, grep nhiều service hoặc tái hiện lỗi.
2. **Tìm kiếm kém chính xác:** truy vấn `message contains "failed"` thu cả những loại lỗi khác nhau.
3. **Phân tích tỷ lệ thất bại khó:** không phân biệt action hay outcome bằng trường chuẩn.
4. **Điều tra sai nguyên nhân:** lấy các log gần nhau về thời gian làm cùng request dù không liên quan.
5. **Giám sát nhiễu:** không có error code ổn định, chỉ còn message tự do có thể đổi từ bản phát hành này sang bản khác.
6. **Thiếu bằng chứng nghiệp vụ:** bản ghi `Updated` không cho biết cái gì thay đổi và transaction đã commit chưa.
7. **Khó xử lý môi trường phân tán:** log từ nhiều replica, queue consumer, background job và HTTP request trộn lẫn.
8. **Tạo áp lực thêm log:** vì mỗi dòng quá nghèo thông tin, đội phát triển có xu hướng log nhiều dòng ở mọi tầng để bù, dễ dẫn tới log storm.

Đổi `log.info("Done")` thành `log.info("Done " + requestId)` chỉ giải quyết một phần. Còn phải làm rõ **done cái gì**, đối tượng và **điểm xác nhận thành công**.

## 3. Context tối thiểu cần có là gì?

Không có một bộ trường bắt buộc áp dụng cho mọi log. Hãy bắt đầu từ **câu hỏi người vận hành sẽ hỏi** và **loại event đang phát**.

| Nhóm câu hỏi | Trường gợi ý | Ví dụ |
| --- | --- | --- |
| **What — chuyện gì?** | `event`, `operation` | `order.create.result`, `CREATE_ORDER` |
| **Which — đối tượng nào?** | `orderId`, `resourceType`, `resourceId` | `ord-42` |
| **Which execution?** | `requestId`, `operationId`, `messageId`, `jobRunId` | `req-101` |
| **Outcome?** | `outcome`, `reasonCode` | `SUCCEEDED`, `ROLE_MISSING` |
| **Where?** | `service.name`, logger name, environment, instance | `orders-api`, `production` |
| **When?** | Timestamp UTC, duration | `2026-11-10T02:00:00Z`, `27ms` |
| **Who?** | Actor ID đã xác thực nếu có ý nghĩa và được phép | `admin-7` |
| **Why?** | Error code, exception type/cause, policy | `STORAGE_UNAVAILABLE` |
| **How related?** | `traceId`, `spanId`, `correlationId` | Một trace/operation liên quan |

**Log context = envelope + event data.** Timestamp, level, logger và service đôi khi đã do backend/collector tự thêm; không cần chép lặp vào message nếu hệ thống chắc chắn lưu được. Những trường mang ý nghĩa nghiệp vụ như action, target, outcome thường phải do chính code phát log cung cấp.

Một bản ghi tốt phải trả lời được ít nhất: **“đã xảy ra điều gì, với đối tượng nào, trong lần xử lý nào, kết quả ra sao?”** — theo mức độ nhạy cảm và mục đích của event.

## 4. Before/after: biến log mơ hồ thành log có nghĩa

| Anti-pattern | Bản ghi hữu ích hơn | Lợi ích |
| --- | --- | --- |
| `INFO Updated` | `event=profile.email.changed userId=u-42 outcome=SUCCEEDED` | Biết loại cập nhật và target |
| `ERROR Failed` | `event=payment.capture.failed paymentId=p-7 errorCode=PROVIDER_TIMEOUT` | Biết action và loại lỗi |
| `INFO Done` | `event=order.create.result orderId=ord-42 outcome=SUCCEEDED` | Biết thao tác và kết quả |
| `WARN Retry` | `event=message.retry_scheduled messageId=evt-9 attempt=3 reason=DEPENDENCY_UNAVAILABLE` | Đặt retry vào lifecycle |
| `INFO Request received` | `event=http.request.received requestId=req-101 route=/api/orders/{id} method=POST` | Liên hệ với một HTTP request |
| `ERROR Database error` | `event=order.persist.failed operationId=op-9 errorCode=DB_CONNECTION_TIMEOUT` kèm Throwable | Có nguyên nhân và ngữ cảnh |
| `INFO Starting` | `event=job.run.started job=nightly-settlement runId=run-72` | Phân biệt các lần chạy job |
| `INFO User authenticated` | `event=auth.login.result outcome=SUCCEEDED actorId=u-42` | Biết loại sự kiện bảo mật |

Các tên trường/event này là **mẫu thiết kế**, không phải format bắt buộc của JUL, Logback, Log4j 2 hay OpenTelemetry. Hãy đặt schema và naming convention thống nhất cho hệ thống.

Không bổ sung `rawEmail`, `password`, `accessToken`, `fullRequestBody` chỉ để “có thêm context”. Context **chất lượng** là thông tin cần thiết và được phép lưu, không phải càng nhiều càng tốt.

## 5. Phân biệt event code, thông điệp tự do và kết quả

**Event code** là một giá trị có ý nghĩa ổn định, ví dụ:

```text
order.create.started
order.create.result
order.persist.failed
payment.authorize.result
message.processing.failed
job.run.completed
auth.login.denied
```

**Message text** dành cho người đọc, có thể được dịch hoặc viết lại. **Outcome** diễn đạt kết quả ở một ranh giới cụ thể:

```json
{
  "event": "order.create.result",
  "operation": "CREATE_ORDER",
  "orderId": "ord-42",
  "outcome": "DENIED",
  "reasonCode": "ROLE_MISSING"
}
```

Dữ liệu này nói rằng **một yêu cầu tạo đơn bị từ chối**, không phải đơn hàng đã được tạo. `order.create.result` là kết quả xử lý thao tác yêu cầu tạo đơn; chỉ đặt `outcome=SUCCEEDED` khi điều kiện thành công thực tế đã thỏa.

Ba mẫu thiết kế phổ biến:

- **Event + outcome:** `event=order.create.result, outcome=SUCCEEDED|DENIED|FAILED`.
- **Event theo mốc:** `order.creation.requested`, `order.created`, `order.creation.denied`.
- **Action + phase + outcome:** `action=CREATE_ORDER, phase=RESULT, outcome=FAILED`.

Chọn một chuẩn có tài liệu. Không dùng `order.created` ngay khi chỉ vừa nhận HTTP request hoặc trước transaction commit; điều đó làm log **sai sự thật**, dù có rất nhiều context.

### 5.1. Context phải bám vào lifecycle thực

Một request HTTP trả `202 Accepted` có thể chỉ chứng minh đã xếp job vào queue; không chứng minh job hoàn tất. Một `Kafka Acknowledgment.acknowledge()` có thể chỉ yêu cầu container ACK/commit theo mode; không nhất thiết xác nhận offset đã durable ngay tại dòng gọi. Một message ghi `Done` trước khi database commit có thể hoàn toàn sai nếu rollback.

Do đó context **quan trọng hơn việc đặt một câu tiếng Anh nghe giống thành công**. Hãy ghi tên mốc chính xác: `accepted`, `processing_started`, `committed`, `delivery_requested`, `retry_scheduled`, `failed`.

## 6. Java 17: chương trình chạy được so sánh log thiếu và có ngữ cảnh

Ví dụ Java 17 này chỉ dùng `java.util.logging` (JUL), **không cần dependency**. Nó in ba dòng:

1. Một log `Done` mơ hồ.
2. Kết quả tạo order **thành công**, có request ID, route, operation, target, outcome và thời gian.
3. Kết quả tạo order **bị từ chối**, có reason code riêng.

Để stdout **xác định**, một handler in đúng `level + message`, không in timestamp hay thread. Các giá trị đều là hằng đã kiểm soát. Dữ liệu production phải dùng structured encoder, validation và redaction đúng chính sách thay vì nối trực tiếp chuỗi tự do.

Lưu file **`ContextualLoggingDemo.java`**:

```java
import java.util.Locale;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ContextualLoggingDemo {
    record Context(String requestId, String route, String operation) {}

    private static void logResult(
            Logger logger,
            Context context,
            String orderId,
            String outcome,
            String reason,
            long durationMs) {

        String message = String.format(
                Locale.ROOT,
                "event=order.create.result requestId=%s route=%s "
                        + "operation=%s orderId=%s outcome=%s "
                        + "reason=%s durationMs=%d",
                context.requestId(),
                context.route(),
                context.operation(),
                orderId,
                outcome,
                reason,
                durationMs);

        logger.info(message);
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.contextual");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler output = new Handler() {
            {
                setLevel(Level.ALL);
            }

            @Override
            public void publish(LogRecord record) {
                if (record != null && isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
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

        logger.addHandler(output);
        try {
            // Anti-pattern: không thể biết "Done" là thao tác nào.
            logger.info("Done");

            logResult(
                    logger,
                    new Context(
                            "req-101",
                            "/api/orders/{id}",
                            "CREATE_ORDER"),
                    "ord-42",
                    "SUCCEEDED",
                    "NONE",
                    27);

            logResult(
                    logger,
                    new Context(
                            "req-102",
                            "/api/orders/{id}",
                            "CREATE_ORDER"),
                    "ord-43",
                    "DENIED",
                    "ROLE_MISSING",
                    4);
        } finally {
            logger.removeHandler(output);
            output.close();
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac ContextualLoggingDemo.java
java ContextualLoggingDemo
```

Kết quả **`stdout` chính xác**:

```text
INFO Done
INFO event=order.create.result requestId=req-101 route=/api/orders/{id} operation=CREATE_ORDER orderId=ord-42 outcome=SUCCEEDED reason=NONE durationMs=27
INFO event=order.create.result requestId=req-102 route=/api/orders/{id} operation=CREATE_ORDER orderId=ord-43 outcome=DENIED reason=ROLE_MISSING durationMs=4
```

### 6.1. Giải thích ví dụ

- `record Context` biểu diễn ba trường liên quan request theo cú pháp Java hiện đại. `record` không tự xác thực `requestId` hay `route`.
- `logger.info("Done")` không thể trả lời đã hoàn thành việc gì.
- Hai dòng sau có cùng `event` và `operation` nhưng khác `requestId`, `orderId`, `outcome`, giúp truy vấn/suy luận riêng.
- `reason=ROLE_MISSING` là **mã lý do** do code quyết định, không phải nội dung error message tùy ý.
- `durationMs` là giá trị cố định để minh họa: trong ứng dụng thật, đo bằng đồng hồ monotonic như `System.nanoTime()` quanh đoạn xử lý cần đo.
- `setUseParentHandlers(false)` tránh thêm bản ghi từ handler cha khi chạy demo.
- Handler tùy chỉnh chỉ in nội dung nhằm có stdout ổn định; nó **không** tạo JSON, không lưu log bền vững, không quản lý rotate và không thay thế collector.
- Toàn bộ context trong ví dụ là chuỗi hằng. **Không dùng cách ghép text này để log raw input không tin cậy**, vì có nguy cơ log injection và parsing lỗi.

Chương trình không truy cập database hoặc API. Hai outcome mô phỏng nhằm minh họa cách thiết kế thông điệp; bản ghi `SUCCEEDED` không phải bằng chứng đã commit một đơn hàng thật.

### 6.2. Kết quả nào dễ truy vấn hơn?

Với ba dòng trên, một bộ lọc khái niệm:

```text
event = order.create.result
AND outcome = DENIED
AND reason = ROLE_MISSING
```

sẽ giúp lọc trường hợp thao tác bị từ chối — **nếu** pipeline lưu/parse các fields như dự định. `INFO Done` không thể được nhóm chính xác theo một operation mà không có ngữ cảnh bên ngoài.

**Mảnh text key=value không tự động thành structured data.** Một backend chỉ lưu một trường `message` nguyên khối sẽ vẫn cần parser. Production nên xuất key-value field qua API có hỗ trợ hoặc encoder JSON phù hợp.

## 7. Từ “message có nhiều chữ” sang structured logging thật

Một log như:

```text
Order failed for order ord-42 because database was not available in region east
```

dễ đọc hơn `Failed`, nhưng vẫn khó truy vấn ổn định: thứ tự câu/wording có thể thay đổi, tên vùng có thể mang ngữ nghĩa không chuẩn, parser phụ thuộc regex.

Một event **có cấu trúc**:

```json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "level": "ERROR",
  "service": "orders-api",
  "event": "order.persist.failed",
  "operation": "SAVE_ORDER",
  "requestId": "req-101",
  "orderId": "ord-42",
  "outcome": "FAILED",
  "errorCode": "STORAGE_UNAVAILABLE",
  "durationMs": 27
}
```

Các giá trị là **minh họa**, không đến từ một ứng dụng thật. Trường `errorCode` phục vụ báo cáo/alert ổn định, không lấy nguyên văn `Exception.getMessage()`.

Một schema có thể chuẩn hóa:

- Tên event dạng `domain.resource.action.phase` hoặc một quy ước thống nhất.
- Enum outcome và errorCode có tập giá trị kiểm soát.
- ID có định dạng/độ dài được validate.
- Tên trường và kiểu dữ liệu cố định (`durationMs` là số, không phải `"27ms"` nếu muốn query số).
- Timestamp, service, environment do tầng đáng tin cung cấp.
- Schema version nếu thay đổi ý nghĩa hoặc các trường bắt buộc.

**Không cố gắng đưa mọi thông tin vào một message duy nhất** nếu log backend có khả năng lưu fields riêng. Đó là điểm khác nhau giữa “thông điệp dài” và “event có cấu trúc”.

## 8. SLF4J và Logback: viết thế nào để có context?

Trong ứng dụng dùng SLF4J, ví dụ phổ biến:

```java
// Mảnh tích hợp: log là org.slf4j.Logger; các biến đã có trong scope.
log.info("event=order.create.result orderId={} outcome={} requestId={}",
        safeOrderId, outcomeCode, validatedRequestId);
```

**Placeholder `{}` không tự biến các đối số thành field JSON.** Nó giúp định dạng và tránh tạo message cuối khi level bị tắt (dù các phép tính tạo tham số đắt tiền vẫn được thực hiện trước). Khi dùng Logback pattern thông thường, kết quả vẫn là một chuỗi.

Với **SLF4J 2.x** và backend/provider tương thích, có thể dùng **fluent key-value API**:

```java
// Mảnh tích hợp: log có kiểu org.slf4j.Logger;
// safeOrderId, validatedRequestId và outcomeCode đã khai báo.
log.atInfo()
        .addKeyValue("event", "order.create.result")
        .addKeyValue("operation", "CREATE_ORDER")
        .addKeyValue("orderId", safeOrderId)
        .addKeyValue("requestId", validatedRequestId)
        .addKeyValue("outcome", outcomeCode)
        .log("Order creation attempt finished");
```

Đây **không phải file Java độc lập**. Cần SLF4J 2.x và logging provider tương ứng. `addKeyValue` gắn thuộc tính vào sự kiện ở mức API; **có xuất thành JSON field hay không** còn tùy backend, encoder/layout và cấu hình. Không mặc định tất cả provider đều render key-value theo một format.

Với Log4j 2 có `ThreadContext` và các API structured tương ứng; với JUL dùng `LogRecord`, resource bundle hoặc custom formatter/handler. **Không trộn cấu hình Logback và Log4j 2**, cũng không coi pattern text là JSON structured log.

### 8.1. Context nên đặt ở đâu?

- **Theo event:** operation, outcome, orderId, errorCode cụ thể của sự kiện.
- **Theo request/trace:** requestId, traceId, tenant scope đã được xác định tin cậy.
- **Theo deployment:** service.name, version, environment, instance/pod ID do logging infrastructure thêm.

Việc sao chép một context request lớn vào mọi log có thể tăng dung lượng và chi phí. Với event log độc lập về nghiệp vụ, chỉ thêm những field thực sự cần cho phân tích và audit.

## 9. MDC: bổ sung ngữ cảnh xuyên các log trong một luồng

Trong SLF4J, **MDC (Mapped Diagnostic Context)** hỗ trợ gắn một số key-value vào ngữ cảnh logging của thread/provider để các event trong một request có thể chia sẻ ID.

Một mảnh mã trong Java web service:

```java
import org.slf4j.MDC;

// Code tích hợp: validatedRequestId là giá trị đã được kiểm tra.
String previous = MDC.get("requestId");
try {
    if (validatedRequestId == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", validatedRequestId);
    }

    processBusinessRequest();
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
```

Đây **không phải chương trình độc lập**; `processBusinessRequest()` và `validatedRequestId` phải do ứng dụng cung cấp.

Các điều kiện quan trọng:

1. **MDC không tự phát log.** Logback/Log4j 2 phải được cấu hình encoder/pattern để xuất giá trị, ví dụ Logback có thể dùng `%X{requestId}`.
2. **Thread pool dùng lại thread.** Nếu không remove/restore trong `finally`, request sau có thể mang nhầm ID từ request trước.
3. **MDC thường liên quan thread.** Khi dùng `CompletableFuture`, executor, callback, reactive processing hay message listener, không mặc định context tự lan qua mọi thread.
4. **Không đưa raw client header thẳng vào MDC.** ID phải được validate hoặc tạo ở gateway/trust boundary theo policy.
5. MDC thích hợp với các trường nhỏ và hữu hạn; không chứa raw payload, object lớn, token hoặc toàn bộ user profile.
6. **Một request có thể gọi nhiều business operation.** MDC requestId không thay thế operationId, transactionId hay event-specific target.

Một log với `requestId` đúng nhưng thiếu `operation` vẫn có thể mơ hồ; MDC là **một công cụ**, không phải phương thuốc duy nhất cho context-free message.

## 10. Context qua bất đồng bộ: Java 17 runnable demo

Trong tác vụ async, một lỗi thường gặp là đặt `requestId` ở thread A, rồi ghi `Done` trên thread B mà không truyền context. Để thấy phương án an toàn, ví dụ sau **truyền một record Context rõ ràng vào nhiệm vụ**, không dựa vào ThreadLocal có thể bị mất.

Lưu file **`AsyncLoggingContextDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class AsyncLoggingContextDemo {
    record Context(String correlationId, String messageId) {}

    private static String process(Context context) {
        return "event=message.processing.result"
                + " correlationId=" + context.correlationId()
                + " messageId=" + context.messageId()
                + " outcome=SUCCEEDED";
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Context context = new Context("corr-01", "msg-07");
            Future<String> result = executor.submit(
                    () -> process(context));
            System.out.println(result.get());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac AsyncLoggingContextDemo.java
java AsyncLoggingContextDemo
```

**Stdout chính xác**:

```text
event=message.processing.result correlationId=corr-01 messageId=msg-07 outcome=SUCCEEDED
```

Ví dụ dùng `ExecutorService` thực nhưng **in string ra stdout**, không tích hợp một logging backend. Mục đích là chứng minh context có thể được mang sang task thông qua dữ liệu truyền tường minh và xuất ở cuối task.

Trong production có thể dùng task decorator, wrapper `Runnable/Callable`, framework context propagation hoặc OpenTelemetry context scope; nếu copy MDC, cần **restore/clear ở task finally**, không chỉ copy vào thread rồi để lại. Trên reactive stack nên dùng context mechanism đúng framework thay vì coi `ThreadLocal` là đủ.

### 10.1. Không nhầm correlation ID với một actor đã được xác thực

`correlationId` giúp tìm các sự kiện cùng luồng; nếu được client tự đặt, nó cũng có thể bị giả mạo. Các sự kiện bảo mật cần tách **actor đã xác thực** khỏi ID tương quan. Trace ID không chứng minh thao tác đã thành công, người dùng có quyền hay dữ liệu đã commit.

## 11. HTTP web logging: một event hoàn chỉnh cần những gì?

Một request có thể đi qua reverse proxy, authentication filter, controller, service và database. Nếu các tầng đều ghi `Request done`, việc tìm lỗi trở nên khó.

Một access event phù hợp:

```json
{
  "event": "http.request.completed",
  "requestId": "req-101",
  "method": "POST",
  "route": "/api/orders",
  "status": 201,
  "durationMs": 38,
  "service": "orders-api",
  "outcome": "SUCCEEDED"
}
```

**Không dùng raw URL/query string thay thế route template** nếu có thể tránh: query có thể chứa token, email hoặc dữ liệu cá nhân; path với ID động gây cardinality cao. `/api/orders/{id}` hữu ích hơn `/api/orders/431928` khi tổng hợp theo endpoint.

Nhưng **status HTTP không luôn tương đương kết quả nghiệp vụ**:

- `202 Accepted` thường chỉ xác nhận tiếp nhận job.
- `200` có thể trả về một trạng thái `PENDING` do ứng dụng định nghĩa.
- Một API có thể trả `200` dù body báo lỗi nghiệp vụ (thiết kế này cần được xem xét).
- Request streaming có thể bị gián đoạn sau khi status/header đã gửi.

Do đó log ở đúng request lifecycle, tránh ghi `completed` khi chỉ mới vào controller. Với Servlet async hoặc reactive processing, thời gian filter kết thúc chưa chắc là thời gian response hoàn tất.

### 11.1. Có cần ghi cả client IP, User-Agent và user ID?

Không mặc định. Những trường này có rủi ro quyền riêng tư và độ tin cậy:

- `User-Agent` do client tự khai, có thể spoof.
- IP gần nhất có thể là proxy/gateway; `X-Forwarded-For` phải đi qua trust policy.
- Raw user ID/tenant ID có thể nhạy cảm; chỉ giữ trong phạm vi cần thiết và được phép.
- Authenticated principal phải đến từ cơ chế xác thực đáng tin, **không** lấy từ request parameter tùy ý.

Một request access event nên tối thiểu hóa dữ liệu mà vẫn phục vụ được debug/điều tra. Log “có đầy đủ mọi header” không phải cải thiện đúng cho anti-pattern thiếu context.

## 12. Message consumer: context phải gắn với delivery và outcome

Một consumer nhận event từ Kafka/RabbitMQ/JMS có thể log `Received`, `Retry`, `Done`. Nếu message được giao lại sau crash/timeout, những dòng này sẽ rất khó ghép.

Một event ví dụ:

```json
{
  "event": "message.processing.failed",
  "consumerGroup": "billing-workers",
  "messageType": "OrderCreated",
  "messageId": "evt-77",
  "correlationId": "corr-01",
  "attempt": 2,
  "source": "orders-topic",
  "errorCode": "DEPENDENCY_UNAVAILABLE",
  "retryable": true
}
```

Tùy broker, có thể thêm **Kafka topic/partition/offset**, RabbitMQ exchange/routing key/delivery tag, hoặc JMS message ID. **Không dùng delivery tag của RabbitMQ như business event ID toàn cục**, và không tự áp offset semantics của Kafka cho JMS.

Quan trọng: log `message.processing.succeeded` **khác** `ack_requested` và `offset_commit_succeeded`. Nếu side effect database đã commit nhưng offset chưa commit, message có thể được xử lý lại. Vì vậy cần **idempotency key/transaction** phù hợp để tránh nhân đôi nghiệp vụ, bên cạnh log đủ ngữ cảnh.

Ở batch consumer, cần phân biệt **batch ID** với **message ID riêng**, và nếu có kết quả partial thì ghi outcome của từng record hoặc summary có count và liên kết theo operation.

## 13. Scheduled job và background task

Với scheduled jobs, một log `Job finished` không phân biệt được nhiều lần chạy hoặc nhiều instance.

Ví dụ:

```json
{
  "event": "job.run.completed",
  "jobName": "nightly-settlement",
  "runId": "run-20261110-01",
  "triggerType": "SCHEDULED",
  "outcome": "PARTIAL",
  "processedCount": 920,
  "failedCount": 3,
  "durationMs": 18420
}
```

Đây là event minh họa. `processedCount`/ `failedCount` cần định nghĩa rõ tính theo record logic, attempts hay side effects; không lấy số log `Processed` để suy ra count.

Nếu job chạy lại, thêm `attempt` hoặc `retryOf` có ý nghĩa. Nếu lỗi được bắt nhưng scheduler cần biết job thất bại, **đừng nuốt exception chỉ sau khi log `Failed`**; xử lý trạng thái job theo scheduler contract.

## 14. Exception logging: thiếu context lẫn mất root cause

Anti-pattern phổ biến:

```java
// Đoạn minh họa cần tránh.
catch (Exception e) {
    log.error("Failed");
}
```

Log này thiếu operation, đối tượng, error code và **không có throwable**. Thậm chí:

```java
// Vẫn sai về chẩn đoán: chỉ giữ text, không có stack trace/cause.
catch (Exception e) {
    log.error("Failed: {}", e.getMessage());
}
```

Tốt hơn tại error boundary:

```java
// Mảnh tích hợp: safeOrderId và log đã khai báo.
// Không log cùng Throwable ở mọi tầng để tránh trùng stack trace.
try {
    createOrder();
} catch (OrderProcessingException failure) {
    log.error("event=order.create.failed orderId={} errorCode={}",
            safeOrderId, "ORDER_CREATE_FAILED", failure);
    throw failure;
}
```

Trong ví dụ, `createOrder()` và `OrderProcessingException` được định nghĩa bởi ứng dụng, không phải file Java độc lập. Với SLF4J phổ biến, Throwable ở vị trí argument cuối được xử lý như cause của logging event. Nếu dùng overload có ambiguity, dạng `log.error("Order creation failed", failure)` nêu rõ Throwable.

**Nguyên tắc:**

1. Khi wrap exception, dùng `new SomeException("context", original)` để giữ `getCause()`.
2. Truyền **Throwable thật** cho logger, không chỉ `getMessage()` hoặc `toString()`.
3. Ghi event code và entity/correlation IDs đã được kiểm duyệt.
4. Ở boundary có quyền quyết định outcome, log một lần đủ thông tin; tránh trùng `ERROR`/stack trace ở repository, service và controller.
5. Đối với validation error dự kiến, không phải lúc nào cũng cần ERROR stack trace; chọn mức log theo tác động.
6. Với lỗi retry, phân biệt lần thử tạm thời và thất bại cuối cùng.
7. Không đưa raw SQL, password, token, payload hoặc stack trace ra HTTP response công khai.

**Log có context nhưng không có Throwable** vẫn có thể thiếu bằng chứng kỹ thuật. **Log có Throwable nhưng thiếu request/operation** vẫn có thể khó tìm trong hệ thống nhiều request. Cần phối hợp cả hai theo yêu cầu.

## 15. Trace, span, requestId và operationId: dùng đúng mục đích

Những ID này không hoàn toàn tương đương:

| ID | Ngữ nghĩa |
| --- | --- |
| `requestId` | Một HTTP request hoặc một điểm vào ứng dụng |
| `traceId` | Chuỗi span theo distributed tracing, có thể qua nhiều service |
| `spanId` | Một span trong trace |
| `correlationId` | Mã liên hệ một nhóm operation/event theo thiết kế |
| `operationId` | Một hành động nghiệp vụ, có thể qua nhiều request/retry |
| `messageId` | Một message logic |
| `attemptId` | Một lần thực thi hoặc delivery |

Trong một hệ thống phân tán, request A có thể tạo message B rồi background job C. Nếu chỉ mang HTTP request ID vào message khi không có context propagation rõ, dễ thiếu liên kết hoặc dùng sai ngữ nghĩa. Nên xác định **định danh xuyên chuỗi nghiệp vụ** và thiết kế truyền qua headers được kiểm tra.

**Trace context không tự lưu event history**: một span có thể sampled, trace exporter có thể mất dữ liệu, và trace ID không phải business event ID. Khi cần audit sự kiện quan trọng, một record audit riêng với durability/integrity phù hợp vẫn cần thiết.

Nếu có OpenTelemetry instrumentation, có thể thêm trace/span IDs vào logs tương ứng, nhưng phải kiểm chứng backend/encoder và propagation. Không mặc định tất cả `logger.info` tự được gắn trace ID.

## 16. Không ghép context bằng giả định về vị trí dòng log

Ví dụ sai:

```text
INFO req-101 BEGIN
INFO processing
ERROR timeout
INFO req-102 BEGIN
INFO processing
INFO done
```

Việc `processing` gần `req-101 BEGIN` **không chứng minh** nó thuộc request 101. Thread pool và concurrency có thể xen kẽ log; việc ship từ nhiều instance cũng có thể thay đổi thứ tự đến.

Thay vào đó, các event quan trọng có correlation ID **trên chính event** hoặc được lưu trong structured context đáng tin:

```text
INFO event=request.started requestId=req-101
WARN event=remote.call.failed requestId=req-101 errorCode=TIMEOUT
INFO event=request.started requestId=req-102
INFO event=order.create.result requestId=req-102 outcome=SUCCEEDED
```

Nếu dùng MDC, phải bảo đảm context được khôi phục đúng khi thread đổi và **được encoder ghi ra**. Nếu app và collector dùng timezone hoặc clock khác, không dựa timestamp đơn độc để suy ra quan hệ nhân quả.

Đối với **trật tự event**, nếu hệ thống cần tái dựng chính xác một workflow nhiều bước, có thể bổ sung `operationId`, `sequenceNo`, transaction version hoặc causation ID. Timestamp UTC hữu ích nhưng không giải quyết clock skew và reorder của distributed ingestion.

## 17. Security: thêm context phải tránh rò rỉ dữ liệu

Thêm `requestBody`, `Authorization`, `password`, `refreshToken` vào message để tìm context là một anti-pattern mới nguy hiểm hơn.

Các nhóm dữ liệu cần cân nhắc:

- **Credential/secret:** password, API key, JWT, session cookie, private key, recovery code; thông thường không được log.
- **Dữ liệu cá nhân:** email, số điện thoại, địa chỉ, định danh người dùng; chỉ ghi nếu thực sự cần, theo quyền và retention.
- **Financial/medical details:** không dump entity hoặc payload đầy đủ khi chỉ cần ID và error code.
- **Raw URL/query:** có thể chứa token hoặc dữ liệu nhạy cảm.
- **Client headers:** User-Agent và correlation ID do client tự khai, có thể bị giả mạo.
- **Throwable message:** có thể chứa SQL, đường dẫn file, hostname, request payload hoặc secret.

Ví dụ `log.info("user={} payload={}", userId, payload)` vừa đắt vừa có thể lộ dữ liệu. Chọn **ID an toàn, loại event, mã lý do và số liệu tổng hợp**.

### 17.1. Log injection

Một chuỗi client tự đặt có thể chứa newline/control characters hoặc các đoạn trông giống log level. Nếu đưa thẳng vào text log:

```text
userName=Alice
ERROR admin permission granted
```

người đọc hoặc parser yếu có thể hiểu thành hai event khác nhau. Nên:

1. Validate định dạng và giới hạn độ dài các ID.
2. Dùng JSON/structured encoder có escaping phù hợp.
3. Loại, escape hoặc thay ký tự điều khiển trong text output.
4. Không cho user-controlled field quyết định tên file, topic, index hay destination.
5. Test dữ liệu unicode, newline, tab, quote, backslash và giá trị quá dài.
6. Không coi `{}` của SLF4J là cơ chế escaping/redaction tự động.

Làm sạch cú pháp cũng **không biến** field do client tự khai thành nguồn đáng tin để xác thực hoặc ra quyết định bảo mật.

## 18. Performance: context hữu ích nhưng không vô hạn

Mỗi field bổ sung tăng bytes/event, chi phí encode, I/O và storage. Với hệ thống hàng nghìn request/giây, việc log quá nhiều có thể ảnh hưởng CPU, GC, network và async queue.

Các lỗi hiệu năng:

- Log toàn bộ object graph bằng `toString()`, có thể gọi lazy-load hoặc duyệt payload lớn.
- Serialize JSON body dù DEBUG đang tắt.
- Ghi stack trace ở mọi retry attempt dẫn đến log storm.
- Thêm raw path, user ID, request ID, trace ID làm **metric labels** gây high cardinality.
- Đưa nhiều dòng chẩn đoán rời rạc thay vì một event có đủ fields.
- Ghi raw context vào mọi statement qua MDC mà không có chủ đích.

Khi giá trị tốn chi phí để tính:

```java
// Mảnh tích hợp: detailsBuilder.build() tốn CPU.
if (log.isDebugEnabled()) {
    log.debug("event=debug.snapshot requestId={} details={}",
            validatedRequestId, detailsBuilder.build());
}
```

Placeholder không làm `detailsBuilder.build()` trở thành lazy vì biểu thức tham số được Java đánh giá **trước lời gọi method**. Giữ guard hoặc dùng Supplier/lazy API phù hợp khi cần.

MDC cho các ID ngắn thường rẻ hơn ghép payload lớn, nhưng chi phí vẫn phụ thuộc logger, formatter và pipeline. Không dùng metric label theo `requestId`; chỉ nên dùng nhãn hữu hạn như `service`, `operation`, `errorCode` có catalog được kiểm soát.

## 19. Đặt context phù hợp với log level và loại sự kiện

Log không ngữ cảnh thường xuất hiện vì lập trình viên thêm `println("here")` hoặc `log.info("ok")` để debug. Hãy chọn **event và level** theo mục đích:

| Trường hợp | Mức thường cân nhắc | Context quan trọng |
| --- | --- | --- |
| Service startup | INFO | service, version, environment, config revision |
| HTTP request completed | Access event/INFO theo policy | route, method, status, duration, requestId |
| Business operation completed | INFO hoặc event nghiệp vụ | operation, entity ID, outcome, operationId |
| Lỗi validation dự kiến | INFO/WARN theo policy | reasonCode, route, requestId |
| Retry tự phục hồi | DEBUG/WARN theo tác động | attempt, maxAttempts, reason, dependency |
| Lỗi không phục hồi tại boundary | ERROR | event/errorCode, requestId, Throwable |
| Message duplicate an toàn | DEBUG/INFO | messageId, source, decision, attempt |
| Thao tác security/audit | Audit channel riêng theo policy | actor đã xác thực, action, target, outcome |
| Log debug chi tiết | DEBUG/TRACE | local operation, các field đã redaction |

Không phải event nào cũng cần `userId`, `traceId` và stack trace. Context phải **đủ cho câu hỏi của loại event**. Cố gắng chuẩn hóa toàn bộ log thành một schema khổng lồ với nhiều field null không nhất thiết tốt hơn việc có các schema theo loại sự kiện.

## 20. Các lỗi thiết kế khác thường đi kèm

### 20.1. Context sai còn nguy hiểm hơn context thiếu

Một worker quên clear MDC khiến log của request B mang `requestId` của A. Điều tra lúc đó có thể đưa ra kết luận sai về hành vi người dùng. Phải restore context theo scope và kiểm thử thread reuse.

### 20.2. Tự tạo ID mới tại mọi tầng

Nếu controller tạo `req-101`, service lại tạo `req-999` mà không giữ liên hệ, không thể ghép chain bằng ID. ID cần **propagate** theo chính sách, chỉ tạo mới tại đúng trust boundary hoặc operation mới.

### 20.3. Dùng một message để khẳng định nhiều kết quả

Ví dụ `Payment processed` sau khi provider chỉ nhận yêu cầu nhưng chưa settle. Nên log `payment.submitted` và `payment.settled` riêng nếu thực tế có hai mốc.

### 20.4. Ghi nhiều log nhưng không có outcome cuối

Một trăm dòng `Start step` không thay thế một event `operation.result` có `outcome`, `durationMs`, count và errorCode hợp lệ.

### 20.5. Không đưa metadata deployment

Nếu cluster có nhiều instance, `ERROR Failed` còn khó hơn khi không biết service/version/pod. Thường nên để logging infrastructure bổ sung các trường deployment thay vì ghép thủ công vào từng message.

### 20.6. Tin tưởng client-supplied IDs

Attacker có thể truyền ID cực dài hoặc giả mạo correlation ID. Validate độ dài/format, chuẩn hóa và dùng server-generated ID khi chính sách yêu cầu. ID tương quan không thay thế principal đã xác thực.

### 20.7. Log context khác nhau giữa các tầng

Controller dùng `user_id`, service dùng `userId`, worker dùng `uid`; các truy vấn tập trung khó thống nhất. Duy trì schema/catalog, test và backward compatibility.

### 20.8. Dựa vào logger name để suy mọi business action

Logger `com.example.OrderService` cho biết thành phần nguồn, nhưng không xác định chính xác method hay thao tác đã thành công. Event code/operation vẫn cần rõ.

### 20.9. Log nhầm sau một catch rồi nuốt lỗi

```java
// Sai: caller có thể không biết xử lý thất bại.
try {
    processPayment();
} catch (Exception e) {
    log.error("Error");
}
```

Mảnh mã chỉ minh họa anti-pattern. Nếu policy yêu cầu retry hoặc rollback, phải giữ trạng thái/throw exception theo đúng contract, không coi log là cơ chế điều khiển lỗi.

### 20.10. Tưởng rằng có log là đã có bằng chứng audit bền vững

App có thể filter/drop log, sidecar bị nghẽn, disk đầy hoặc collector mất network. Audit bắt buộc phải có policy durability/integrity, retention, quyền đọc và đối soát riêng; một event nhiều context vẫn có thể bị mất.

## 21. Kiểm thử chất lượng context trong logging

Đừng chỉ test `logger.info` đã được gọi. Hãy test **thông tin cần để điều tra** và **tính chính xác**:

| Kịch bản | Điều phải xác nhận |
| --- | --- |
| Operation thành công | Có event, operation, target, `SUCCEEDED` sau success boundary |
| Bị từ chối vì thiếu quyền | `DENIED`, reasonCode; không ghi nhầm thành công |
| Validation thất bại | Có field hợp lệ, không lộ payload |
| Database transaction rollback | Không có event `committed` sai |
| Exception bị wrap nhiều tầng | Throwable/cause chain được giữ |
| Hai request đồng thời | Mỗi event gắn đúng requestId, không lấy của request khác |
| Thread pool reuse | MDC được clear/restore, không leak context |
| CompletableFuture/executor | Context được truyền đúng hoặc chủ động không có |
| Background job retry | attempt, runId, outcome riêng mỗi lần |
| Kafka/Rabbit redelivery | message ID và delivery attempt không bị nhầm |
| Thiếu header correlation | Có fallback, không NPE |
| ID chứa newline/control | Không tạo dòng log giả |
| Field có token hoặc PII | Secret bị redact/không xuất tới sink |
| Logger level/filter thay đổi | Hiểu event nào có thể bị tắt và vì sao |
| Collector timeout/drop | Không suy rằng emit = persisted |
| Metric high-cardinality | Không tạo label theo user/request ID |
| JSON encoder | Field type, escaping, Throwable và timestamp đúng |
| Version schema thay đổi | Query cũ không hiểu sai nghĩa event mới |

Một hướng test integration:

1. Cấu hình **test appender/handler** thu log events ở một lớp riêng.
2. Gọi business handler với một `requestId` cố định và state giả lập.
3. Assert **event code, outcome, IDs, errorCode**; không chỉ so khớp một câu free text.
4. Với thất bại, assert `Throwable` không bị mất.
5. Với concurrent executions, chạy nhiều task và kiểm tra từng event có đúng context.
6. Thử parser/JSON exporter tới collector test nếu pipeline có nhiều tầng.
7. Xác minh không có password/token/secret/PII ngoài policy.
8. Dùng marker hoặc event ID để phát hiện missing/duplicate khi collector retry.

Trong JUL có thể kiểm tra `LogRecord.getThrown()` và `getMessage()`; trong Logback có thể dùng test appender với logging events; trong Log4j 2 dùng cơ chế test appender tương ứng. Nếu thay đổi backend/encoder, cần kiểm thử lại **nơi lưu cuối** chứ không chỉ JVM.

### 21.1. Cách review một dòng log

Một cuộc code review có thể đặt các câu hỏi:

- Nếu chỉ thấy **một dòng này** tại hệ thống logs tập trung, có biết chuyện gì đã xảy ra không?
- Có cách phân biệt thành công, từ chối và thất bại không?
- Có thể tìm mọi log của một operation/request/message không?
- Context có từ nguồn đáng tin hay dữ liệu user tự khai?
- Đã ghi đúng mốc commit/ACK/response completion chưa?
- Có trường nào chứa secret, raw payload hoặc ID có cardinality cao không?
- Có đang log trùng stack trace hoặc lặp event vô ích không?
- Nếu backend đổi từ pattern sang JSON, schema có còn ổn định không?

**Không nhất thiết cần một log riêng cho từng phương thức**. Một số nơi chỉ cần metric/tracing; hãy đặt log ở điểm **có sự kiện đáng giải thích**, tránh tạo thêm noise.

## 22. Quy trình nâng cấp hệ thống đang có nhiều log mơ hồ

Nếu dự án đã có hàng nghìn dòng `Done`, `Start`, `Failed`, không cần sửa tất cả trong một commit. Một cách làm có thứ tự:

1. **Inventory theo rủi ro:** tìm những log ở payment, auth, data export, order, message retry, API critical path.
2. **Nhóm theo event:** xác định mỗi dòng đang nói về request lifecycle, business operation, error hay debug progress.
3. **Đặt schema nhỏ:** `event`, `operation`, `target ID`, `outcome`, `requestId` và `errorCode` khi cần.
4. **Chuẩn hóa cách lấy context:** middleware, authenticated principal, message headers, operation ID; không dùng static mutable field chung.
5. **Chọn ranh giới phát event:** sau commit, sau quyết định deny, sau retry scheduled, ở error boundary thích hợp.
6. **Nâng cấp encoder:** nếu muốn query field, dùng structured logging thật và kiểm tra provider/collector.
7. **Test concurrency và async:** ngăn MDC leak, mất correlation, log out-of-order gây hiểu nhầm.
8. **Loại log dư thừa:** khi đã có một event đầy đủ, bỏ bớt các dòng `here`/`done` không còn giá trị.
9. **Thêm alert dựa trên mã lỗi chuẩn:** không dựa vào message wording thay đổi liên tục.
10. **Đánh giá cost và retention:** context hữu ích nhưng phải có kiểm soát dung lượng và bảo mật.

Trước/sau nên được đo bằng **khả năng trả lời một câu hỏi điều tra thật**. Ví dụ: “Trong 30 phút gần nhất có bao nhiêu lần CREATE_ORDER bị DENIED vì ROLE_MISSING trong service orders-api?” Nếu schema mới trả lời được mà không cần grep thủ công, đó là cải thiện thực tế.

## 23. Checklist triển khai log có ngữ cảnh

- [ ] Mỗi event quan trọng có **tên hành động/event code** ổn định.
- [ ] Mỗi bản ghi kết quả có **outcome** chính xác tại ranh giới nghiệp vụ.
- [ ] Có target ID/loại target khi cần phân biệt đối tượng.
- [ ] Có `requestId`, `operationId`, `messageId` hoặc `runId` phù hợp với loại workload.
- [ ] Không nhầm trace/correlation IDs với actor đã xác thực.
- [ ] Service, environment, deployment version và timestamp được logging infrastructure thêm đáng tin.
- [ ] Logger/event fields được encoder xuất thành structured data khi cần phân tích.
- [ ] MDC được restore/clear và propagate đúng qua thread pool/async.
- [ ] Với exception, giữ **Throwable/cause chain** và tránh log lặp ở mọi tầng.
- [ ] Không ghi `SUCCEEDED` trước commit hoặc gọi một ACK request là durable ACK.
- [ ] Không log raw password, token, cookies, body, query string hoặc PII không cần.
- [ ] Escape/validate input, chống log injection và áp giới hạn độ dài.
- [ ] Không dùng requestId/userId/raw path làm metric label high-cardinality.
- [ ] Log volume, rotation, backpressure và collector delivery được giám sát.
- [ ] Test event fields, business outcome, concurrency, async và readback tại sink.
- [ ] Đối với audit bắt buộc lưu, dùng retention/durability/integrity đúng yêu cầu, không dựa riêng vào diagnostic log.

**Kết luận:** **“Log message không ngữ cảnh”** không phải lỗi vì câu quá ngắn, mà vì bản ghi **không đủ thông tin có thể tin cậy để nói điều gì đã xảy ra, ở đâu, với đối tượng nào, trong lần xử lý nào và có kết quả gì**. Cách khắc phục là thiết kế **event code, context đúng scope, correlation ID, outcome và error code**, đặt log ở ranh giới thực tế, dùng structured logging khi cần phân tích và **giữ dữ liệu tối thiểu, an toàn**. Một event ngắn nhưng có cấu trúc và đúng ngữ nghĩa thường hữu ích hơn nhiều dòng `Done`/`Failed` dài mà không thể liên kết.
