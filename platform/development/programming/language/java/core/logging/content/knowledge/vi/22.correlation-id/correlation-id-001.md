# Correlation ID là gì trong Java Logging?

**Correlation ID** là một **định danh dùng để liên kết các sự kiện log thuộc cùng một yêu cầu, tác vụ hoặc quy trình xử lý**. Khi một request đi qua API gateway, service đặt hàng, service thanh toán và hệ thống gửi thông báo, các thành phần có thể tạo ra hàng chục hoặc hàng trăm dòng log. Nếu các dòng đó mang **cùng một Correlation ID**, người vận hành có thể tìm lại toàn bộ những dấu vết liên quan mà không phải đoán theo thời gian hay nội dung message.

Ví dụ đơn giản:

```text
INFO  correlationId=cid-0001 service=checkout-api  event=checkout.received
INFO  correlationId=cid-0001 service=inventory     event=stock.reserved
WARN  correlationId=cid-0001 service=payments      event=payment.retry
INFO  correlationId=cid-0001 service=payments      event=payment.authorized
INFO  correlationId=cid-0002 service=checkout-api  event=checkout.received
```

Bốn dòng đầu thuộc cùng một quy trình; dòng cuối thuộc quy trình khác. **Tìm theo `correlationId=cid-0001`** giúp lọc ra bốn sự kiện liên quan, ngay cả khi chúng do các service hoặc thread khác nhau phát ra.

Correlation ID là **metadata để tương quan (correlate)**, không phải bằng chứng rằng giao dịch đã thành công, cũng không phải mã xác thực hay khóa bảo mật. Bản thân việc thêm ID **không tự giải quyết lỗi**, nhưng giúp trả lời nhanh: *“Những bước nào đã xảy ra trước khi yêu cầu này thất bại, ở thành phần nào và theo thứ tự nào?”*

## 1. Vì sao cần Correlation ID?

### 1.1. Một yêu cầu tạo ra nhiều log

Trong một ứng dụng Java đơn giản, nhiều lớp có thể cùng ghi log:

```text
HTTP /checkout
   |
   v
CheckoutController        INFO request received
   |
   v
CheckoutService           INFO validating cart
   |
   +--> InventoryClient    INFO stock reserved
   |
   +--> PaymentClient      WARN payment retry
   |                       INFO payment succeeded
   v
CheckoutController        INFO response sent
```

Không có correlation key, người điều tra phải dựa vào thời điểm, tên thread và message. Khi nhiều request chạy song song, những log có thể đan xen. Trên hệ thống nhiều instance, timestamp cũng có độ lệch đồng hồ hoặc log đến collector muộn; **chỉ so thời gian không đủ để nối đúng request**.

Một Correlation ID duy nhất được gắn nhất quán trong chuỗi xử lý giúp:

- **Tìm toàn bộ log của một request hoặc workflow** trên các service, khi chúng cùng gửi về hệ thống tìm kiếm.
- **Phân biệt các request đồng thời** có message, endpoint hoặc user giống nhau.
- **Xác định điểm thất bại** giữa API, service, database client và các phụ thuộc ngoài.
- **Liên kết với ticket hỗ trợ** khi người dùng cung cấp một mã tham chiếu không nhạy cảm.
- **Đối chiếu retry và fallback** theo quy tắc xử lý đã công bố.
- **Giảm thời gian điều tra**, vì câu query theo ID thường rõ hơn tìm bằng message text.

Tuy nhiên, Correlation ID không tự bảo đảm log được thu thập đầy đủ. Event vẫn có thể bị lọc theo level, mất trong queue async, lỗi file/network hoặc bị xóa theo retention. ID giúp **liên kết các record có tồn tại**, không thể khôi phục record chưa bao giờ được ghi hoặc đã mất.

### 1.2. Một ID có thể đi qua nhiều thread và JVM

Tên thread như `http-nio-8080-exec-4` hoặc `pool-3-thread-1` thường **không phải định danh request**. Thread pool tái sử dụng thread; một request cũng có thể tiếp tục trên nhiều thread khác nhau. Khi xử lý qua HTTP, Kafka/RabbitMQ hoặc background jobs, dữ liệu đi sang JVM khác.

Do đó correlation key cần được **truyền tường minh theo context của công việc**, chứ không suy ra từ thread name, process ID hay một biến static toàn cục.

## 2. Phân biệt Correlation ID, Request ID, Trace ID và Span ID

Những tên này liên quan nhưng **không mặc nhiên đồng nghĩa**.

| Loại ID | Ý nghĩa và phạm vi | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| **Correlation ID** | Nhóm những event cùng một giao dịch logic hoặc workflow theo quy ước ứng dụng. | `cid-0001` | Có thể bao trùm một request hoặc nhiều bước async; phạm vi phải được định nghĩa. |
| **Request ID** | Xác định một request cụ thể, thường ở ranh giới HTTP/API. | `req-17` | Một workflow có thể gồm nhiều request, mỗi request có ID riêng. |
| **Trace ID** | Xác định một distributed trace trong hệ thống tracing. | `0123456789abcdef0123456789abcdef` | Có định dạng và ngữ nghĩa theo tracing implementation, không phải tự tạo tùy ý. |
| **Span ID** | Xác định một span bên trong một trace. | `0123456789abcdef` | Một trace thường có nhiều span với cùng traceId nhưng spanId khác nhau. |
| **Transaction ID** | Định danh một transaction nghiệp vụ hoặc database tùy hệ thống. | `tx-73` | Không nhất thiết trùng request hay trace. |
| **Idempotency Key** | Nhận diện ý định/thao tác để xử lý yêu cầu lặp không gây hiệu ứng trùng. | `idem-452` | **Không dùng thay** Correlation ID hay trace ID; có ý nghĩa kiểm soát nghiệp vụ riêng. |

**Ví dụ nhiều định danh cùng tồn tại:**

```json
{
  "eventName": "payment.authorized",
  "correlationId": "cid-0001",
  "requestId": "req-17",
  "traceId": "0123456789abcdef0123456789abcdef",
  "spanId": "0123456789abcdef",
  "orderId": "ord-42",
  "outcome": "success"
}
```

Một tổ chức có thể quyết định dùng `traceId` làm khóa correlation chính và không phát thêm `correlationId` riêng. Điều đó **hợp lý nếu được quy định rõ** và tracing thực sự có mặt ở các bước cần liên kết. Một tổ chức khác có workflow nhiều giờ hoặc nhiều ngày có thể cần `correlationId` ổn định qua nhiều trace/request.

**Không tự copy `requestId` sang `traceId`** hoặc điền một chuỗi bất kỳ chỉ để dashboard có dữ liệu. Trace/span ID cần lấy từ tracing context hợp lệ; khi không có trace, xuất vắng mặt/null theo schema thay vì gán ID giả.

### Ví dụ về phạm vi

- Một lệnh gọi HTTP đơn lẻ: `correlationId` có thể trùng `requestId` nếu quy ước hệ thống là **một request = một correlation scope**.
- API ghi nhận đơn rồi queue job xử lý thanh toán: `correlationId` có thể giữ qua HTTP và job; `requestId` chỉ thuộc request ban đầu.
- Retry cùng một thao tác: thường giữ Correlation ID logic để tìm tất cả lần thử, nhưng ghi thêm `attempt` hoặc `attemptId` theo từng lần.
- Người dùng đặt hai đơn khác nhau: cần quyết định rõ chúng có phải hai correlation scopes độc lập; không dùng một ID cho mọi hoạt động của một user hoặc session nếu làm log trở nên quá rộng.

## 3. Cấu trúc của một log có Correlation ID

Có thể ghi ở dạng text:

```text
2026-11-09T12:00:00Z INFO  correlationId=cid-0001 service=checkout-api event=checkout.received orderId=ord-42
2026-11-09T12:00:01Z WARN  correlationId=cid-0001 service=payment-service event=payment.retry attempt=2
2026-11-09T12:00:02Z INFO  correlationId=cid-0001 service=payment-service event=payment.authorized
```

Hoặc structured JSON/NDJSON:

```json
{"timestamp":"2026-11-09T12:00:00Z","level":"INFO","service":"checkout-api","correlationId":"cid-0001","eventName":"checkout.received","orderId":"ord-42"}
{"timestamp":"2026-11-09T12:00:01Z","level":"WARN","service":"payment-service","correlationId":"cid-0001","eventName":"payment.retry","attempt":2}
{"timestamp":"2026-11-09T12:00:02Z","level":"INFO","service":"payment-service","correlationId":"cid-0001","eventName":"payment.authorized"}
```

Các dòng là **dữ liệu minh họa**, không phải stdout của chương trình ở mục thực hành. Khi field `correlationId` là một **JSON key thực sự**, collector có thể query trực tiếp theo field. Nếu chỉ ghi `"correlationId=cid-0001"` trong `message`, khả năng truy vấn còn phụ thuộc text parser và không mặc nhiên là structured logging.

Schema nên làm rõ:

| Field | Kiểu dữ liệu | Ý nghĩa |
| --- | --- | --- |
| `timestamp` | String ISO 8601/RFC 3339 có timezone | Thời điểm event. |
| `level` | String theo quy ước backend | Mức quan trọng. |
| `service` | String | Service tạo log. |
| `eventName` | String | Tên sự kiện ổn định. |
| `correlationId` | String | ID nhóm event trong cùng correlation scope. |
| `requestId` | String hoặc absent | Request cụ thể khi có. |
| `traceId` / `spanId` | String hoặc absent | Tracing context hợp lệ khi được bật. |
| `orderId` / `paymentId` | String hoặc absent | Đối tượng nghiệp vụ, chỉ khi cần và được phép. |
| `attempt` | Number | Lần thử hiện tại, đơn vị/quy ước bắt đầu phải rõ. |
| `outcome` / `errorCode` | String theo enum | Kết quả và mã lỗi dễ phân tích. |

**Tên trường, kiểu dữ liệu và ngữ nghĩa phải ổn định.** Không để một service dùng `correlationId`, service khác dùng `corr_id`, còn service thứ ba ghi ID vào `message` nếu mục tiêu là query xuyên hệ thống mà không có quy tắc mapping. Giá trị phải nằm ở **field value**, không biến ID thành tên key động.

## 4. Correlation ID được tạo và lấy từ đâu?

Ứng dụng có thể nhận ID từ một hệ thống tin cậy ở phía trước, hoặc tạo mới tại **ranh giới entry point** nếu chưa có.

Một luồng phổ biến:

```text
Client / Gateway
  |
  | HTTP request (có thể có X-Correlation-ID)
  v
API boundary
  +--> nếu incoming ID hợp lệ và policy cho phép: dùng ID đó
  +--> nếu thiếu/không hợp lệ: tạo ID mới
  |
  v
Business services
  +--> ghi vào log context cho request
  +--> truyền ID qua HTTP/message/job khi cần
  |
  v
Response
  +--> có thể trả lại correlation ID ở response header
```

**Chọn chính sách nguồn tin cậy:**

1. Nếu **gateway đáng tin cậy** phát ID, các service nội bộ thường sử dụng ID từ gateway theo hợp đồng.
2. Nếu ID được **client ngoài Internet tự gửi**, xem đó là **input không tin cậy**, không tự cho rằng nó là ID nội bộ hợp lệ.
3. Có thể cho phép reuse ID client sau khi validate; hoặc tạo ID server-side và lưu ID client ở trường riêng nếu cần đối chiếu. Quyết định tùy kiến trúc, quyền riêng tư và chính sách chống giả mạo.
4. Nếu một service được gọi độc lập qua job/message không có correlation context hợp lệ, hãy tạo một ID mới cho **scope mới**, không lấy giá trị còn sót từ thread.
5. **Không đổi ID ở mọi tầng**; nếu mỗi service tự tạo ID không có mapping thì liên kết xuyên service bị đứt.

### Kiểu định danh

UUID phiên bản 4 là một lựa chọn phổ biến để tạo ID khó trùng với công cụ chuẩn Java:

```java
// Mã minh họa bên trong một method Java.
String correlationId = java.util.UUID.randomUUID().toString();
```

Đoạn trên **không độc lập**, nhưng method của JDK có sẵn. Có hệ thống dùng ULID/UUIDv7 hoặc ID do gateway tạo để phục vụ sắp xếp/quan sát; **không bắt buộc một định dạng duy nhất** miễn thỏa yêu cầu uniqueness, bảo mật, kích thước, khả năng truyền và schema.

ID thường nên:

- Đủ tính duy nhất trong phạm vi hệ thống và thời gian retention.
- Giới hạn chiều dài để tránh header/log quá lớn.
- Có **bảng chữ cái được phép**; tránh newline, tab và ký tự điều khiển.
- Không chứa token, email, số điện thoại, mật khẩu, định danh nhạy cảm hoặc dữ liệu nghiệp vụ không cần thiết.
- Không dễ bị nhầm với authorization token. **Biết Correlation ID không cấp quyền đọc log, truy cập hồ sơ hay thao tác nghiệp vụ**.

### Header HTTP có phải chuẩn chung?

Tên `X-Correlation-ID` được dùng trong nhiều ứng dụng nhưng **không phải tiêu chuẩn bắt buộc cho mọi hệ thống HTTP**. Một số hệ thống sử dụng `X-Request-ID`, `Correlation-Id` hoặc quy ước riêng. Muốn tích hợp cần thống nhất **tên header, validate, cách forward và cách tạo ID mới** trên toàn chuỗi.

Đối với distributed tracing, W3C Trace Context dùng các header như `traceparent`/`tracestate` với định dạng riêng; không tự đặt chuỗi Correlation ID tùy ý vào `traceparent`. Khi dùng OpenTelemetry hoặc tracing framework, để instrumentation xử lý format/propagation theo hợp đồng của nó.

## 5. Truyền Correlation ID giữa các service

### 5.1. HTTP synchronous

Giả sử service A gọi service B:

```text
Client
  |
  | X-Correlation-ID: cid-0001
  v
Service A
  | LOG: correlationId=cid-0001 event=order.created
  |
  | HTTP request to Service B
  | X-Correlation-ID: cid-0001
  v
Service B
  | LOG: correlationId=cid-0001 event=payment.authorized
  v
HTTP response
```

Lời gọi HTTP **phải truyền ID tường minh** hoặc dùng một interceptor/client instrumentation phù hợp. Việc `MDC.put("correlationId", id)` trên thread của service A **không tự chèn header** cho `HttpClient` hoặc HTTP library bất kỳ.

Mẫu Java 17 với `java.net.http.HttpRequest`, **đoạn minh họa không độc lập**:

```java
import java.net.URI;
import java.net.http.HttpRequest;

// Giả sử id đã được xác minh, uri là URI tin cậy của service B.
HttpRequest outbound = HttpRequest.newBuilder(uri)
        .header("X-Correlation-ID", id)
        .GET()
        .build();
```

Trong mã nguồn thực tế, `import` cần ở đầu file; `uri` và `id` phải có giá trị hợp lệ. Cần tránh forward các header do client cung cấp **mà chưa được xác minh** vào hệ thống nội bộ. Nếu outbound là request khác về scope, chính sách có thể cần tạo correlation mới và giữ liên kết cha–con trong field riêng.

### 5.2. HTTP response và trải nghiệm hỗ trợ

Có thể đưa ID vào response header:

```text
HTTP/1.1 500 Internal Server Error
X-Correlation-ID: cid-0001
Content-Type: application/json

{"errorCode":"PAYMENT_TIMEOUT","correlationId":"cid-0001"}
```

Đây là **response minh họa**. Hiển thị ID trong phản hồi có thể giúp support tìm log cùng sự kiện. Nhưng **không trả stack trace, thông tin nội bộ hoặc dữ liệu cá nhân nhạy cảm** kèm ID. Phần hỗ trợ truy vấn log phải được xác thực/phân quyền độc lập; ID không phải secret nhưng cũng không phải quyền truy cập.

### 5.3. Message queue và event-driven processing

Khi Service A phát message tới consumer:

```text
Service A: correlationId=cid-0001
   |
   | Message:
   | headers.correlationId=cid-0001
   | payload=PaymentRequested
   v
Queue / Topic
   |
   v
Service B:
   read trusted/validated correlationId from message metadata
   establish processing scope
   log event=payment.received
   finally: clear/restore context
```

Không nhất thiết tên field message header giống HTTP header; cần contract rõ ràng. Khi message retry hoặc được xử lý ở worker mới, **giữ ID logic** nếu đó vẫn là cùng một workflow. Đồng thời ghi `messageId`, `attempt` hoặc `deliveryId` để phân biệt lần xử lý vật lý. Nếu job được tách thành một workflow độc lập, tạo correlation ID mới và gắn `parentCorrelationId` hoặc liên kết được định nghĩa rõ thay vì gộp mọi event vào một nhóm quá rộng.

### 5.4. Scheduled job và background processing

Batch job không có HTTP request vẫn có thể dùng Correlation ID để liên kết các event trong **một lần chạy**. Ví dụ `jobRunId` có thể là correlation key theo chính sách, nhưng cần tránh dùng một ID vĩnh viễn cho mọi lần chạy của scheduled task.

Một lần chạy job nên có ID mới hoặc kế thừa một ID từ tác vụ kích hoạt đúng theo yêu cầu nghiệp vụ. Scope rõ ràng giúp việc chạy lại, retry và hỗ trợ khôi phục không làm lẫn log của những lần thực thi khác nhau.

## 6. Đưa Correlation ID vào log bằng MDC (SLF4J + Logback)

Trong Java, dùng **SLF4J** làm logging API và **Logback Classic** làm backend là một kiến trúc phổ biến. `MDC` (*Mapped Diagnostic Context*) cho phép lưu các key–value theo context thực thi, thường gắn với thread hiện tại. Một khi encoder/layout của Logback được cấu hình để đọc MDC, các lời gọi `LOG.info(...)` có thể tự động hiển thị `correlationId` mà không phải truyền ID vào từng message.

Đoạn mã **minh họa trong một method**, giả định `LOG` và `correlationId` đã tồn tại:

```java
org.slf4j.MDC.put("correlationId", correlationId);
try {
    LOG.info("event=checkout.started");
    doBusinessWork();
    LOG.info("event=checkout.completed");
} finally {
    org.slf4j.MDC.remove("correlationId");
}
```

Nếu backend có pattern:

```xml
<pattern>%level correlationId=%X{correlationId:-none} %logger - %msg%n</pattern>
```

thì Logback có thể in field tương ứng, ví dụ:

```text
INFO correlationId=cid-0001 demo.CheckoutService - event=checkout.started
```

**Đây là text pattern, chưa phải JSON structured field**. Muốn query theo JSON field `correlationId`, dùng encoder/layout structured tương thích và xác nhận dữ liệu MDC được xuất thành key riêng. Một pattern chỉ chứa `%msg` sẽ không tự thêm Correlation ID.

### Cảnh báo về scope và thread pool

MDC thường có phạm vi **thread**, còn HTTP request/job là **phạm vi nghiệp vụ**. Pool thread có thể xử lý request A rồi B; nếu code của A quên cleanup thì log B có thể mang ID của A. Vì vậy:

- Đặt Correlation ID tại **entry boundary** (middleware/filter/interceptor/job handler).
- Dọn trong `finally` khi scope kết thúc, kể cả khi throw/return.
- Nếu có **scope lồng nhau** trên cùng key, **khôi phục giá trị cũ** thay vì chỉ remove.
- Không dùng `MDC.clear()` bừa bãi ở tầng không sở hữu mọi context field; nó có thể xóa trace/span ID do instrumentation quản lý.
- Không tự cho rằng task `CompletableFuture` hoặc `ExecutorService` sẽ nhận MDC của caller.
- Có chính sách khi request mới **không có ID**: tạo ID hợp lệ hoặc để absent theo contract, tuyệt đối không kế thừa giá trị cũ.

### Scope lồng nhau và khôi phục giá trị cũ

Ví dụ một scope con tạm dùng Correlation ID khác (nếu kiến trúc yêu cầu):

```java
// Mã minh họa: LOG và childCorrelationId đã tồn tại.
String previous = org.slf4j.MDC.get("correlationId");
try {
    org.slf4j.MDC.put("correlationId", childCorrelationId);
    LOG.info("event=child.started");
} finally {
    if (previous == null) {
        org.slf4j.MDC.remove("correlationId");
    } else {
        org.slf4j.MDC.put("correlationId", previous);
    }
}
```

Với request scope thông thường, **không đổi Correlation ID nếu vẫn cùng workflow**. Ví dụ scope con dùng ID khác chỉ áp dụng khi đã định nghĩa ranh giới mới và cách liên kết với parent. Nếu cần nhận diện bước con đơn giản, thường nên **giữ correlationId và thêm `operationId` hoặc `spanId` riêng**, thay vì thay chính correlation ID.

## 7. Log4j 2 ThreadContext và JUL

### Log4j 2

Log4j 2 có `ThreadContext` để gắn context theo thread/scope:

```java
// Mã minh họa, LOG và correlationId đã tồn tại.
org.apache.logging.log4j.ThreadContext.put(
        "correlationId", correlationId
);
try {
    LOG.info("event=payment.started");
} finally {
    org.apache.logging.log4j.ThreadContext.remove("correlationId");
}
```

Với PatternLayout Log4j 2, `%X{correlationId}` thường được dùng để xuất value từ ThreadContext map; muốn JSON, chọn layout/encoder phù hợp, ví dụ template JSON trong module tương ứng. Không giả định mọi bridge/facade có cùng context adapter: kiểm tra backend thực sự đang chạy và artifact provider/bridge cần thiết.

### Java Util Logging

`java.util.logging` (JUL) cung cấp `Logger`, `LogRecord`, `Handler` và `Formatter` nhưng **không có MDC chuẩn tích hợp tương đương SLF4J MDC**. Muốn gắn Correlation ID vào JUL có thể:

- Truyền ID tường minh vào message hoặc event-specific data/`LogRecord`.
- Dùng một formatter và event wrapper có schema cố định để xuất JSON/text.
- Thiết kế scope propagation riêng của ứng dụng nếu cần.
- Chuyển JUL qua SLF4J bằng bridge có chủ đích khi kiến trúc chọn backend thống nhất; **bridge không tự sinh Correlation ID**.

Bài thực hành ở mục 9 dùng JUL và **đi qua hai service mô phỏng bằng hai thành phần Java trong một JVM**, để thấy cơ chế truyền ID tường minh. Ví dụ này không cần Maven hay backend bên ngoài.

## 8. Truyền context qua ExecutorService và CompletableFuture

Một vấn đề thường gặp:

```text
HTTP thread
    MDC.correlationId = cid-0001
    |
    | executor.submit(...)
    v
Pool worker thread
    MDC.correlationId = ?   (không tự bảo đảm)
```

**Sai lầm:** chỉ `MDC.put` ở caller rồi kỳ vọng worker có cùng giá trị. Worker có thể không có ID hoặc mang ID lỗi thời từ công việc trước nếu cleanup không tốt.

Hai cách an toàn:

1. **Truyền Correlation ID như một tham số bất biến của task** (rõ ràng, dễ test).
2. **Chụp snapshot context tại lúc submit**, cài vào worker trong `try` và khôi phục/clear ở `finally`, hoặc dùng task decorator/context propagation mechanism do framework hỗ trợ.

Mẫu truyền một field **tường minh**:

```java
// Mã minh họa; executor, correlationId, orderId, LOG được khai báo.
String capturedId = correlationId;

java.util.concurrent.Future<?> task = executor.submit(() -> {
    String before = org.slf4j.MDC.get("correlationId");
    try {
        if (capturedId == null) {
            org.slf4j.MDC.remove("correlationId");
        } else {
            org.slf4j.MDC.put("correlationId", capturedId);
        }

        LOG.info("event=payment.started orderId={}", orderId);
    } finally {
        if (before == null) {
            org.slf4j.MDC.remove("correlationId");
        } else {
            org.slf4j.MDC.put("correlationId", before);
        }
    }
});
```

**Đoạn trên không phải chương trình standalone.** Nó minh họa một **key duy nhất**, không truyền cả MDC map. Nếu framework quản lý trace/security context, cần cơ chế propagation chính thức tương ứng; chỉ chép `correlationId` không truyền được toàn bộ tracing scope.

Với `CompletableFuture`, một stage có thể chạy trên common pool hoặc thread thực thi completion. Không suy ra context hiện tại chỉ từ tên method có hay không có hậu tố `Async`. Thiết lập context trong đúng callback/task scope và cleanup sau khi nó chạy.

**Đừng nhầm async appender với async nghiệp vụ.** AsyncAppender có thể lấy snapshot context của logging event tại lúc phát log, nhưng nó không tự đặt correlationId cho một task mới trước khi task đó gọi logger.

### Correlation ID qua thread ≠ Correlation ID qua mạng

Ngay cả khi đã giải quyết MDC propagation trong cùng JVM, outbound HTTP hay message queue vẫn cần **truyền header/metadata qua ranh giới tiến trình**. ThreadLocal không thể vượt qua network. Ngược lại, nhận đúng header ở service B nhưng không gắn nó vào logging context của B cũng khiến log của B thiếu ID.

## 9. Java 17 chạy độc lập: một Correlation ID qua hai thành phần xử lý

Ví dụ sau chỉ dùng JDK 17 và **JUL**, không cần thư viện ngoài. Nó minh họa:

- Hai thao tác checkout có **hai Correlation ID khác nhau**.
- Mỗi thao tác phát một log ở phần **checkout-api** và một log ở **payment-service** mô phỏng.
- Bước payment chạy qua **single-thread ExecutorService** để chứng minh ID được truyền **tường minh**, không dựa vào ThreadLocal.
- `Future.get()` giúp output theo thứ tự xác định; formatter không có timestamp.
- Hai event của cùng thao tác có **cùng Correlation ID** nhưng service/event/level khác nhau.
- Logger chỉ giữ một Handler tùy chỉnh; `setUseParentHandlers(false)` tránh log thêm từ handler gốc.

**Đây là mô phỏng hai thành phần trong một JVM.** Đối với hai JVM thật, phải dùng HTTP header hoặc message metadata như mục 5.

### 9.1. Mã nguồn CorrelationIdDemo.java

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class CorrelationIdDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.correlation");

    private record Event(
            String correlationId,
            String service,
            String eventName,
            String orderId
    ) {}

    private static final class EventFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Event event = (Event) record.getParameters()[0];

            return record.getLevel().getName()
                    + " | correlationId=" + event.correlationId()
                    + " | service=" + event.service()
                    + " | event=" + event.eventName()
                    + " orderId=" + event.orderId() + "\n";
        }
    }

    private static void log(Level level, Event event) {
        LogRecord record = new LogRecord(level, event.eventName());
        record.setLoggerName(LOG.getName());
        record.setParameters(new Object[]{event});
        LOG.log(record);
    }

    private static void checkout(
            String correlationId,
            String orderId,
            boolean decline,
            ExecutorService executor
    ) throws Exception {
        log(Level.INFO, new Event(
                correlationId,
                "checkout-api",
                "checkout.received",
                orderId
        ));

        // Chụp hai giá trị bất biến trước khi gửi task sang worker.
        String idForWorker = correlationId;
        String orderForWorker = orderId;

        Future<?> result = executor.submit(() -> {
            if (decline) {
                log(Level.WARNING, new Event(
                        idForWorker,
                        "payment-service",
                        "payment.declined",
                        orderForWorker
                ));
            } else {
                log(Level.INFO, new Event(
                        idForWorker,
                        "payment-service",
                        "payment.authorized",
                        orderForWorker
                ));
            }
        });

        try {
            result.get(); // Đợi xong trước khi xử lý checkout kế tiếp.
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw ex;
        }
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        Handler handler = new StreamHandler(bytes, new EventFormatter());
        handler.setLevel(Level.ALL);
        handler.setEncoding(StandardCharsets.UTF_8.name());
        LOG.addHandler(handler);

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            // Dùng ID cố định để output của bài học tái lập được.
            checkout("cid-0001", "ord-42", false, executor);
            checkout("cid-0002", "ord-43", true, executor);
        } finally {
            executor.shutdown();
            LOG.removeHandler(handler);
            handler.close();
        }

        System.out.print(bytes.toString(StandardCharsets.UTF_8));
    }
}
```

### 9.2. Biên dịch và chạy

Lưu thành `CorrelationIdDemo.java` và chạy bằng JDK 17 trở lên:

```bash
javac CorrelationIdDemo.java
java CorrelationIdDemo
```

**Standard output chính xác của chương trình:**

```text
INFO | correlationId=cid-0001 | service=checkout-api | event=checkout.received orderId=ord-42
INFO | correlationId=cid-0001 | service=payment-service | event=payment.authorized orderId=ord-42
INFO | correlationId=cid-0002 | service=checkout-api | event=checkout.received orderId=ord-43
WARNING | correlationId=cid-0002 | service=payment-service | event=payment.declined orderId=ord-43
```

### 9.3. Tại sao ví dụ cho thấy Correlation ID hoạt động?

1. Mỗi lời gọi `checkout(...)` nhận **một correlationId do entry boundary cung cấp**; demo dùng chuỗi cố định để output không đổi.
2. Log của checkout-api chứa ID cùng với event `checkout.received`.
3. Worker của payment-service nhận ID **qua biến `idForWorker` được chụp trước khi submit**, không giả định một thread khác tự biết context của caller.
4. Trong checkout thứ nhất, cả hai record có `cid-0001`. Checkout thứ hai có `cid-0002`, giúp phân biệt hai luồng nghiệp vụ.
5. `Executors.newSingleThreadExecutor()` tái sử dụng cùng một worker nhưng mỗi task có ID **tường minh**; không có stale MDC/ThreadLocal.
6. `Future.get()` đảm bảo log payment của checkout 1 được phát trước khi bắt đầu checkout 2, nên thứ tự output dự kiến cố định. Bản chất hệ thống phân tán thật **không đảm bảo** toàn bộ log giữa các service đến collector theo đúng thứ tự này.
7. `EventFormatter` lấy metadata từ `LogRecord` parameters, không tự “nhớ” ID của task trước. Đây là kỹ thuật minh họa JUL, không phải MDC built-in của JUL.
8. `handler.close()` flush dữ liệu của `StreamHandler` vào `ByteArrayOutputStream` trước khi in stdout.
9. `WARNING` trong JUL tương ứng mức cảnh báo của JUL, không phải một API `WARN` thống nhất trên mọi logging framework.

### 9.4. Nếu muốn quan sát fail case

Thử xóa việc truyền `idForWorker` hoặc đặt một ID cứng sai cho payment-service và so output. Bạn sẽ thấy hai log của cùng checkout không thể được nối bằng cùng một Correlation ID.

**Không coi mã sửa sai này là cách triển khai thật**: mục tiêu của nó chỉ là hiểu vì sao ID cần được propagate. Trong production hãy dùng một API wrapper hoặc middleware chịu trách nhiệm truyền correlationId, thay vì sao chép thao tác này thủ công tại mọi lời gọi.

### 9.5. Hạn chế cố ý của demo

- Không có HTTP server/client thật hoặc message broker; chỉ có hai thành phần mô phỏng.
- Không tạo UUID ngẫu nhiên vì muốn stdout deterministic; production cần ID có tính duy nhất đủ mạnh.
- Không xây hệ thống tracing; chỉ minh họa correlation, không phát `traceId`/`spanId` giả.
- Không minh họa JSON encoder hoặc SLF4J MDC trực tiếp; event metadata đã được truyền tường minh trong JUL.
- Không chứng minh log không thể mất: StreamHandler chỉ là đích ghi cho demo, không phải hệ thống lưu log bền vững.

## 10. Correlation ID và structured logging

Đối với công cụ quan sát, một field có cấu trúc giúp truy vấn hơn một chuỗi message:

**Text-only message:**

```json
{"level":"INFO","message":"cid-0001 checkout.received orderId=ord-42"}
```

**Có field riêng:**

```json
{
  "level": "INFO",
  "eventName": "checkout.received",
  "correlationId": "cid-0001",
  "orderId": "ord-42",
  "service": "checkout-api"
}
```

Nếu ứng dụng dùng SLF4J 2.x, có thể gắn **per-event key–value**:

```java
// Đoạn minh họa, LOG và correlationId đã tồn tại.
LOG.atInfo()
   .addKeyValue("eventName", "checkout.received")
   .addKeyValue("correlationId", correlationId)
   .log("Checkout received");
```

`addKeyValue` cung cấp event attributes ở mức facade, nhưng việc **xuất chúng thành các JSON field riêng** phụ thuộc encoder/backend. Chỉ dùng `PatternLayoutEncoder` in `%msg` có thể không xuất các key-value đã đính kèm. Cần test bằng output JSON thực tế của pipeline.

### Có nên luôn ghi Correlation ID trong mọi log?

Không nhất thiết:

- **Application startup** chưa có request/job context: chỉ cần resource metadata như service, instance.
- **Health checks hoặc background activity** có thể không thuộc correlation scope giống request; nếu cần, định nghĩa scope riêng.
- **Log của một request đang xử lý** nên có ID thống nhất ở các bước quan trọng để truy vết.
- **Một event chỉ dùng nội bộ ở mức DEBUG** có thể vẫn được gắn context nếu cần chẩn đoán, nhưng phải cân nhắc chi phí và chính sách dữ liệu.

Nếu schema yêu cầu `correlationId` trên mọi record, phải định nghĩa rõ giá trị khi không có scope. **Không dùng ID của request trước** để lấp field bị thiếu. Missing/null có thể đúng hơn một ID giả.

## 11. Correlation ID có phải thông tin bảo mật không?

**Không phải credential.** Correlation ID giúp tra cứu các bản ghi liên quan, nhưng người biết ID **không được mặc nhiên truy cập log**. Hệ thống quản trị vẫn cần xác thực và phân quyền. Đồng thời, correlationId **có thể cho phép liên kết hành vi** qua nhiều hệ thống, nên cần xử lý theo chính sách dữ liệu và quyền riêng tư.

### Xử lý header không tin cậy

Nếu ứng dụng nhận `X-Correlation-ID` trực tiếp từ client:

- **Giới hạn chiều dài** và kiểu ký tự; tránh header nhiều megabyte hoặc ký tự điều khiển.
- **Không cho input chứa newline/CRLF** lọt vào log text mà chưa xử lý; structured encoder phải escape đúng.
- **Không lưu ID chứa email, access token, session cookie hoặc PII** do client nhét vào header.
- **Không cho phép ID quyết định tenant, quyền truy cập hay quyền đọc log**.
- Cân nhắc **tạo lại ID server-side** nếu header không hợp lệ hoặc policy yêu cầu.
- Nếu có nhiều reverse proxy, xác định ranh giới tin cậy để biết header nào do gateway phát và header nào do client giả mạo.
- Nếu ID được trả trong response cho mục đích hỗ trợ, không trả kèm dữ liệu lỗi nhạy cảm chỉ vì có cùng ID.

Ví dụ một quy tắc validation *minh họa* cho ID dạng ASCII chữ/số, dấu gạch dưới và dấu gạch ngang, độ dài từ 8 đến 64:

```java
// Mã minh họa, không phải class standalone.
boolean valid = incoming != null
        && incoming.matches("[A-Za-z0-9_-]{8,64}");
```

Regex này **không bắt buộc** và sẽ không phù hợp với mọi hệ thống nếu định dạng cần dấu chấm, ký tự khác hoặc độ dài khác. ID `cid-0001` trong demo có 8 ký tự và phù hợp regex trên; UUID dạng chuẩn có 36 ký tự cũng có thể phù hợp. Validation **không xác thực tính đáng tin cậy** của ID, chỉ đảm bảo hình thức.

### Tránh biến ID thành tên field

**Sai:**

```json
{"cid-0001":"payment.authorized"}
```

**Đúng:**

```json
{"correlationId":"cid-0001","eventName":"payment.authorized"}
```

Tên key giữ ổn định cho phép collector/indexer định nghĩa schema, còn giá trị biến động nằm trong field value. Correlation ID thường có cardinality cao; nó hữu ích để tìm kiếm nhưng có thể tốn chi phí indexing. Không tự động gắn từng correlationId thành label của mọi metric time series.

## 12. Retry, timeout, duplicate message và correlation scope

Correlation ID là **định danh để liên kết quan sát**, không phải cơ chế bảo đảm xử lý đúng một lần.

### Retry

Một payment request có thể thất bại lần đầu rồi thành công lần hai:

```json
{"correlationId":"cid-0001","eventName":"payment.retry","attempt":1,"errorCode":"TIMEOUT"}
{"correlationId":"cid-0001","eventName":"payment.authorized","attempt":2,"outcome":"success"}
```

Giữ cùng `correlationId` giúp thấy toàn bộ quá trình, còn `attempt` làm rõ từng lần. Nếu dùng một ID hoàn toàn mới cho mỗi retry mà không có liên kết, việc điều tra quá trình phục hồi sẽ khó hơn.

### Timeout và request có thể tiếp tục ở backend

Client có thể timeout, nhưng service phía sau vẫn xử lý. Hai phía vẫn có thể ghi cùng Correlation ID khi đó là cùng một thao tác logic, nhưng **ID không chứng minh side effect đã commit**. Cần truy vấn trạng thái nghiệp vụ hoặc cơ chế idempotency/transaction riêng.

### Duplicate delivery

Message broker có thể giao lại cùng một message. Giữ `correlationId` giúp nhóm các event cùng workflow, nhưng cần thêm `messageId`, `deliveryId` hoặc `attempt` khi muốn phân biệt mỗi lần nhận. Không dùng Correlation ID làm khóa duy nhất của từng event nếu một workflow có nhiều event.

### Saga và workflow dài hạn

Một saga có thể đi qua nhiều request, event và batch job trong nhiều giờ. Có thể giữ `correlationId` ở cấp saga và thêm `requestId`/`traceId` cho từng bước. Nếu correlation scope quá rộng, ví dụ một ID dùng cả tháng cho mọi hoạt động của một tài khoản, lượng log truy vấn trở nên lớn và dễ trộn các thao tác không liên quan. Hãy định nghĩa **ranh giới logic** của một correlation scope.

## 13. Correlation ID và Distributed Tracing

**Correlation ID logging** và **distributed tracing** bổ trợ nhau:

| Khía cạnh | Correlation ID trong log | Distributed tracing |
| --- | --- | --- |
| Mục tiêu chính | Tìm các event cùng scope. | Quan sát quan hệ nhân quả và thời gian của các span. |
| Định danh | Có thể là ID do ứng dụng/gateway định nghĩa. | Trace ID và Span ID theo tracing context. |
| Cấu trúc | Thường là thuộc tính chung trên log record. | Cây/đồ thị span, parent–child, duration và attributes. |
| Quan hệ thứ tự | Có thể suy luận một phần theo timestamp và eventName. | Có cấu trúc span cho các quan hệ đã được instrument. |
| Yêu cầu tích hợp | Log context, propagation, encoder và collector. | Instrumentation/propagator, exporter và backend tracing. |
| Phạm vi | Có thể bao quát cả workflow nhiều trace nếu quy định vậy. | Một distributed trace cụ thể. |

**Không thay trace ID bằng correlation ID tùy ý.** Nếu dùng OpenTelemetry và đã có `traceId`, `spanId`, nên đưa đúng những ID từ active span vào log event để có thể mở trace tương ứng. Nếu muốn liên hệ nhiều trace thuộc một workflow, thêm `correlationId`/`workflowId` theo contract thay vì phá định dạng trace.

Một câu query kiểu:

```text
correlationId = "cid-0001"
```

có thể truy xuất log từ nhiều service nếu chúng thật sự cùng phát field và được ingest. Nhưng để biết RPC nào là parent/child của RPC nào, distributed tracing cho nhiều thông tin chính xác hơn một ID log đơn thuần.

## 14. Lỗi thường gặp khi triển khai Correlation ID

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Log service A có ID, service B không có | Chưa truyền HTTP header/message metadata hoặc B chưa gắn vào logging context. | Kiểm tra hai phía outbound/inbound và encoder. |
| Mỗi service tạo ID mới | Không nhận hoặc không tin cậy propagation từ entry boundary. | Thống nhất cơ chế và ranh giới tạo ID. |
| Log của request B mang ID của A | MDC/ThreadContext không được dọn trên pooled thread. | Dùng `try/finally`, restore/clear và test thread reuse. |
| Async task mất ID | Chỉ set MDC ở caller thread. | Capture/propagate context khi submit hoặc truyền ID tường minh. |
| Query theo `correlationId` không trả kết quả | ID chỉ nằm trong `message`, không thành JSON field, hoặc tên field không nhất quán. | Kiểm tra structured encoder và index mapping. |
| Tên field `correlationId`/`corr_id`/`cid` trộn lẫn | Không có schema chung. | Chọn canonical field, migration/mapping có kiểm soát. |
| Dùng cùng ID cho mọi request của user | Scope quá rộng, truy vấn lẫn nhiều thao tác. | Tạo ID theo request/workflow, không theo tài khoản dài hạn. |
| Retry bị coi là giao dịch mới không liên quan | Thay ID mỗi lần thử mà thiếu parent link. | Giữ ID logic và thêm attempt/attemptId. |
| Log có correlation ID nhưng trace UI không mở được | ID không phải trace ID thực tế. | Dùng traceId từ tracer, không sao chép ID tự tạo. |
| Client đưa header chứa ký tự xuống dòng | Không validate/sanitize dữ liệu không tin cậy. | Validate input, giới hạn độ dài, JSON escaping. |
| Nhân viên support biết ID rồi xem được log riêng tư | Hệ thống dùng ID thay xác thực/phân quyền. | Bắt buộc authorization độc lập và audit truy cập. |
| Dashboard hiển thị ID nhưng thiếu lỗi quan trọng | Logging bị filter/drop, collector lỗi hoặc retention quá ngắn. | Giám sát pipeline và retention; ID không đảm bảo thu đủ log. |
| Có log sai tenantId nhưng đúng correlationId | Context khác bị stale hoặc bị gắn nhầm. | Quản lý đầy đủ scope context; ID không tự kiểm chứng tenant. |
| Tạo ID từ timestamp đơn thuần | Có thể trùng trong hệ thống concurrency cao. | Dùng cơ chế tạo ID có độ duy nhất phù hợp, ví dụ UUID. |
| Client thay đổi correlation ID qua từng API call | Thiếu quy ước workflow giữa các call. | Định nghĩa khi nào reuse ID và khi nào tạo request-level ID riêng. |

## 15. Checklist thiết kế và kiểm thử Correlation ID

1. **Phạm vi:** Một Correlation ID đại diện cho một HTTP request, một job hay một workflow nhiều bước?
2. **Nguồn tạo:** Gateway/entry service tạo ID hay nhận từ nguồn khác? Ranh giới tin cậy được xác định chưa?
3. **Định dạng:** ID có đủ tính duy nhất, độ dài hợp lý, ký tự an toàn và không chứa secret/PII?
4. **Propagation:** Đã thống nhất HTTP header, message metadata và cách forward ID sang service khác?
5. **MDC/ThreadContext:** ID được đặt đúng scope, dọn hoặc khôi phục kể cả khi exception chưa?
6. **Async:** Task ở executor/CompletableFuture/reactive pipeline có nhận đúng ID, không dùng stale context?
7. **Schema:** JSON log có field `correlationId` thực, tên/type/semantic nhất quán giữa service?
8. **Tracing:** Có phân biệt correlationId, requestId, traceId và spanId? Dùng tracer khi cần trace thực?
9. **Retry:** Giữ ID logic và bổ sung attempt/messageId để phân biệt các lần thử?
10. **Lỗi và missing context:** Không dùng ID cũ; tạo mới hoặc biểu diễn absent/null theo contract?
11. **Bảo mật:** ID không thay quyền truy cập; header được validate; log không chứa token hoặc dữ liệu nhạy cảm?
12. **Vận hành:** Collector có giữ field, index có thể truy vấn, retention đủ cho thời gian điều tra?
13. **Kiểm thử liên service:** Cùng ID có được ghi ở entry và downstream trên một workflow thật?
14. **Kiểm thử concurrency:** Hai request liên tiếp dùng chung worker không lẫn ID A/B?
15. **Kiểm thử lỗi:** Retry, timeout, exception, cancellation và queue redelivery có giữ/khôi phục đúng ID?

### Bài tập tự thực hiện

- Thử gắn một `correlationId` mới cho request A và request B; viết query lọc chỉ các event của A.
- Viết HTTP client gửi `X-Correlation-ID` hợp lệ, thêm log ở service nhận, xác minh cả hai phía dùng cùng ID.
- Trên một single-thread executor, cố ý bỏ `finally` khi dùng MDC, quan sát request B có bị nhiễm ID của A không; sau đó sửa bằng scope cleanup/restore.
- Với JSON logger, chứng minh `correlationId` là **field riêng** thay vì chỉ là một phần của `message`.
- Bổ sung `requestId` và `traceId` đúng nguồn; kiểm tra không tự gán correlation ID vào trace ID sai định dạng.
- Thử retry cùng logic operation nhiều lần, giữ correlation ID nhưng thay `attempt`, rồi kiểm tra query trả đủ các lần thử.

## 16. Tự kiểm tra kiến thức

1. Correlation ID giúp giải quyết vấn đề gì khi log của nhiều request xuất hiện xen kẽ?
2. Vì sao thread name hoặc process ID không thay thế Correlation ID?
3. Correlation ID và traceId/spanId khác nhau thế nào?
4. Khi một workflow kéo dài qua HTTP, queue và background job, ID nên được tạo và truyền ở đâu?
5. Vì sao `MDC.put(...)` trên service A không tự thêm HTTP header cho service B?
6. Nếu một client gửi `X-Correlation-ID` có CRLF hoặc độ dài bất thường, server cần làm gì?
7. Tại sao ID đúng trong message text chưa có nghĩa JSON collector tìm được trường `correlationId`?
8. Khi worker thread tái sử dụng, vì sao việc không dọn MDC có thể gán sai ID cho request sau?
9. Trong Java 17 demo, vì sao cả `checkout-api` và `payment-service` có cùng ID dù log được ghi từ hai thread?
10. Correlation ID có ngăn thanh toán bị thực hiện hai lần khi retry không?
11. Nếu hệ thống đã có OpenTelemetry traceId, có bắt buộc phải tạo thêm correlationId không?
12. Vì sao biết một Correlation ID không được cho phép xem log riêng tư của người khác?

**Kết luận:** **Correlation ID là khóa liên kết các log thuộc cùng một request hoặc workflow theo định nghĩa của ứng dụng**. Giá trị của nó nằm ở việc **tạo ID đúng ranh giới, truyền qua các service và thread, gắn vào event có cấu trúc, giữ schema ổn định, dọn context sau scope và xác minh đầu ra thật**. Dùng Correlation ID đúng cách giúp điều tra lỗi phân tán nhanh hơn; nó bổ sung, chứ không thay thế, distributed tracing, idempotency, kiểm soát bảo mật và độ tin cậy của hệ thống logging.