# Thông tin request khi lỗi trong Java Logging

Khi một HTTP request thất bại, chỉ ghi `NullPointerException`, `Bad request` hoặc `Payment failed` thường chưa đủ để điều tra. Người xử lý sự cố còn cần biết **yêu cầu nào gặp lỗi, đi qua chức năng nào, trả trạng thái gì, mất bao lâu và có liên hệ với những log nào khác**. Tập hợp thông tin này được gọi là **request context** (ngữ cảnh yêu cầu).

Trong phần **Exception logging** của Java Core Logging, mục tiêu của việc ghi request context là giúp truy ngược từ một lỗi tới đúng lượt xử lý, xác định tác động, kết nối các sự kiện giữa thành phần và đối chiếu được với phản hồi HTTP. **Request context không đồng nghĩa với việc ghi toàn bộ request.** Log cần đủ để chẩn đoán nhưng phải loại bỏ dữ liệu bí mật, dữ liệu cá nhân không cần thiết và những giá trị đầu vào không đáng tin cậy.

## 1. Vì sao exception cần ngữ cảnh request?

Giả sử ứng dụng ghi:

```text
ERROR java.lang.IllegalStateException: Cannot reserve inventory
```

Thông báo cho biết một ngoại lệ đã phát sinh, nhưng không trả lời được request nào gây ra lỗi, endpoint nào bị ảnh hưởng, đó là lỗi nội bộ hay lỗi dữ liệu, và cần tìm log nào trước đó.

Một event có thêm ngữ cảnh sẽ hữu ích hơn:

```text
2026-11-09T10:15:30.125Z ERROR event=http_request_failed requestId=req-81 traceId=trace-27 method=POST route=/orders/{id}/reserve status=500 errorCode=INVENTORY_RESERVE_FAILED durationMs=128
java.lang.IllegalStateException: Cannot reserve inventory
    at com.example.orders.InventoryService.reserve(InventoryService.java:...)
    ...
```

Đây là **log minh họa**, không phải output của chương trình phía dưới. Dấu `...` đại diện cho những stack frame phụ thuộc mã nguồn thực tế.

Nhờ `requestId=req-81`, người điều tra có thể gom các log của cùng request. `method=POST` và `route=/orders/{id}/reserve` chỉ rõ loại thao tác mà không tiết lộ nguyên văn URL. `status=500` cho biết kết quả mà ứng dụng ghi nhận. `errorCode` là mã phân loại ổn định; `durationMs` giúp phát hiện dấu hiệu chậm hoặc timeout. Stack trace vẫn cần để biết luồng gọi và nguyên nhân kỹ thuật.

Điểm cần phân biệt:

- **Exception** giải thích lỗi kỹ thuật xảy ra ở đâu và nguyên nhân gần nhất của nó.
- **Request context** cho biết lỗi xảy ra trong hoạt động nào và liên quan tới lượt xử lý nào.
- **HTTP response** cho biết ứng dụng phản hồi cho phía gọi như thế nào; response status và chi tiết nội bộ không nhất thiết giống nhau.
- **Trace/metric** có thể bổ sung luồng giữa dịch vụ và mức ảnh hưởng, nhất là khi nhiều request thất bại đồng thời.

## 2. Những trường nên cân nhắc ghi khi request thất bại

| Trường | Ý nghĩa | Ví dụ an toàn / lưu ý |
| --- | --- | --- |
| `timestamp` | Mốc thời gian của event, nên có timezone rõ ràng | `2026-11-09T10:15:30.125Z` |
| `level` | Mức nghiêm trọng theo chính sách hệ thống | `WARN`, `ERROR`; JUL: `WARNING`, `SEVERE` |
| `event` | Tên sự kiện ổn định để tìm kiếm | `http_request_failed` |
| `requestId` | Định danh để gom log trong một lượt xử lý | `req-81` |
| `traceId`, `spanId` | Liên kết với distributed tracing nếu được triển khai | Giá trị do tracing system sinh/kiểm soát |
| `method` | Phương thức HTTP | `GET`, `POST`, `PUT`, `DELETE` |
| `route` / `endpoint` | Mẫu route định danh chức năng | `/orders/{id}` thay vì URI có ID và query nhạy cảm |
| `status` | HTTP status được quyết định hoặc ghi nhận | `400`, `404`, `500`, `503` |
| `errorCode` | Mã lỗi ổn định, có thể tổng hợp thống kê | `INVALID_QUANTITY`, `UPSTREAM_TIMEOUT` |
| `durationMs` | Thời gian xử lý, dùng để đánh giá chậm/timeout | `128`; đo bằng đồng hồ monotonic |
| `exceptionType` và `cause` | Kiểu exception và nguyên nhân kỹ thuật | `IllegalArgumentException` cùng `Throwable` |
| `service`, `component` | Dịch vụ hoặc thành phần phát event | `order-service`, `OrderController` |
| `dependency`, `attempt` | Bước phụ thuộc hoặc retry gây lỗi, nếu liên quan | `inventory-api`, `attempt=2` |

**Không bắt buộc mọi event có mọi trường.** Hãy ghi các trường cần để điều tra loại lỗi đang xét, thống nhất tên và kiểu dữ liệu giữa các thành phần. Ví dụ, một lỗi không có HTTP request (job nền, consumer message) nên dùng `jobId`, `messageId` hay `runId` thay vì giả tạo `method=GET`.

### Request ID và trace ID khác nhau thế nào?

`requestId` thường dùng để nối tất cả log thuộc một yêu cầu tại một dịch vụ hoặc toàn chuỗi dịch vụ nếu được truyền tiếp. Hệ thống có thể chọn cách cấp ID riêng; **không có chuẩn bắt buộc** mọi ứng dụng phải đặt tên hoặc sinh ID theo cùng thuật toán.

`traceId` thường định danh toàn bộ distributed trace; `spanId` định danh một bước trong trace. Chúng hữu ích khi request đi qua gateway, service A, service B và cơ sở dữ liệu. **Một request ID không tự động tạo ra distributed trace**; muốn liên kết cần tạo/truyền context và cấu hình instrumentation phù hợp.

Nếu nhận ID từ header do client cung cấp, cần có chính sách rõ ràng về mức tin cậy, định dạng, độ dài và quyền ghi. Cách phổ biến là ứng dụng/gateway kiểm tra ID nhận được hoặc tự sinh ID đáng tin cậy. Không dùng chuỗi tùy ý từ người dùng như thể nó đã là correlation ID nội bộ.

## 3. Ghi đúng đường dẫn và nội dung request mà không rò rỉ dữ liệu

Khi exception xuất hiện, người viết thường muốn ghi `request.getRequestURI()`, `request.getQueryString()`, toàn bộ headers hoặc body. Việc đó có thể đưa dữ liệu bí mật vào log.

**Nên ưu tiên mẫu route** do router/framework xác định:

```text
method=GET route=/users/{userId}/orders
```

**Hạn chế ghi URL nguyên văn**, chẳng hạn:

```text
GET /users/987654/orders?access_token=secret&email=someone@example.test
```

URL thực tế có thể chứa user ID, email, token hay nội dung tìm kiếm riêng tư. Ngay cả path parameter cũng có thể nhạy cảm. Nếu bắt buộc lưu một định danh phục vụ điều tra, chọn loại được phê duyệt, áp dụng mask/hash có chủ đích và xác định rõ thời gian lưu cũng như quyền truy cập.

Với HTTP headers, chỉ đưa vào log những giá trị đã được xem xét và cho phép. **Không ghi nguyên văn** `Authorization`, `Cookie`, `Set-Cookie`, API key, session token, client certificate, mật khẩu hay thông tin thanh toán. `User-Agent`, `Referer`, `X-Forwarded-For` cũng là dữ liệu có thể dài, không tin cậy hoặc chứa thông tin riêng tư; chỉ ghi khi có mục đích rõ ràng và đã xử lý an toàn.

**Client IP:** `remoteAddr` có thể là địa chỉ reverse proxy, trong khi `X-Forwarded-For` do client có thể giả mạo nếu proxy chưa thiết lập ranh giới tin cậy. Nếu cần IP để điều tra, phải xác định đúng chuỗi proxy đáng tin cậy và tuân thủ chính sách lưu trữ dữ liệu cá nhân. Đừng suy ra “người gây lỗi” chỉ từ một IP.

**Request body:** có thể chứa JSON lớn, ảnh, mật khẩu, khóa, thẻ thanh toán và dữ liệu nghiệp vụ nhạy cảm. Không đưa toàn bộ body vào log exception theo mặc định. Thường chỉ cần `errorCode`, tên thao tác, số lượng bản ghi, ID nội bộ được phép lưu và vài trường đã kiểm tra.

## 4. Kết nối request context với exception ở đúng ranh giới

Một cách tổ chức phổ biến của ứng dụng HTTP:

```text
HTTP request
   |
   v
Middleware / Filter: nhận hoặc sinh requestId, mở context, ghi thời điểm bắt đầu
   |
   v
Router / Controller: xác định route template và gọi xử lý nghiệp vụ
   |
   v
Service -> Repository / HTTP client / dependency
   |
   +-- Exception được ném lên ranh giới xử lý lỗi
   v
Exception handler: phân loại lỗi, quyết định HTTP status và errorCode
   |
   v
Ghi một event thất bại có request context + Throwable
   |
   v
HTTP response và đóng/dọn context
```

Sơ đồ chỉ thể hiện **trách nhiệm logic**, không áp đặt một lớp filter/controller cố định cho mọi framework. Ứng dụng thật có thể phân loại exception trong global exception handler, middleware, interceptor hoặc error boundary khác; quan trọng là có **một nơi chịu trách nhiệm chính** log lỗi cho mỗi request.

Nếu lớp repository đã log toàn bộ exception và ném lại, service tiếp tục log rồi controller log lần nữa, cùng một thất bại có thể tạo nhiều stack trace trùng lặp. Quy ước hữu ích là:

- Thành phần thấp có thể thêm ngữ cảnh vào exception và **giữ nguyên cause**.
- Ranh giới có đủ request context và kết quả HTTP log exception ở mức thích hợp.
- Những lần retry trung gian có thể log ngắn gọn `attempt`, `dependency`, `outcome`; chỉ coi thao tác là thất bại cuối cùng khi chính sách retry đã kết thúc.
- Nếu một framework đã tự ghi lỗi có đầy đủ dữ liệu, hãy kiểm tra trước khi thêm cơ chế ghi trùng ở ứng dụng.

Trạng thái log phải phản ánh **kết quả thực tế được xử lý**: lỗi đầu vào được phân loại thành `400` không nên tự động được log ở mức nghiêm trọng như `500` ngoài dự kiến. Nếu kết nối bị ngắt trước khi response được gửi, trường `status` trong log có thể chỉ là **trạng thái dự kiến**, cần nêu rõ hoặc dùng trường `responseCommitted`/`outcome` phù hợp.

## 5. Phân loại lỗi và chọn mức log cho request thất bại

| Tình huống | HTTP status thường gặp | Mức log nên cân nhắc | Lưu ý |
| --- | --- | --- | --- |
| Payload không hợp lệ do client | `400`, `422` tùy API | `INFO`/`WARN`; JUL `INFO`/`WARNING` | Thường là tình huống dự kiến, tránh stack trace dày đặc nếu không giúp điều tra |
| Không tìm thấy tài nguyên | `404` | `INFO` hoặc `WARN` theo bối cảnh | Không phải mọi `404` đều là lỗi server |
| Không xác thực/không đủ quyền | `401`, `403` | Chính sách bảo mật riêng | Không ghi credentials hoặc token; hạn chế lộ chi tiết truy cập |
| Bị giới hạn lưu lượng | `429` | `INFO`/`WARN` tùy thiết kế | Ghi mã lý do và chính sách rate limit ở mức cho phép |
| Lỗi phụ thuộc tạm thời | `502`, `503`, `504` nếu API dùng mã này | `WARN` hoặc `ERROR` theo tác động | Nêu dependency, timeout, retry và outcome cuối |
| Ngoại lệ không dự kiến | `500` | `ERROR`; JUL `SEVERE` | Giữ stack trace và correlation ID; phản hồi client vẫn chung chung |

Bảng chỉ là **định hướng**: mã HTTP, level và việc có ghi stack trace hay không tùy hợp đồng API, tính nghiêm trọng, khả năng phục hồi và chính sách vận hành. Ví dụ `IllegalArgumentException` có thể đại diện cho đầu vào không hợp lệ ở ranh giới xác thực, nhưng cũng có thể là lỗi lập trình nội bộ. **Không ánh xạ mọi exception chỉ dựa vào tên lớp.**

Thông điệp phản hồi cho client cần được thiết kế riêng với thông điệp log nội bộ: client có thể nhận `{"errorCode":"INVALID_QUANTITY","requestId":"req-81"}`, trong khi log giữ exception và bối cảnh kỹ thuật. Không trả stack trace hoặc đường dẫn file nội bộ trong HTTP response công khai.

## 6. Ví dụ Java 17 chạy độc lập: log lỗi cùng request context

Chương trình dưới đây chạy với **JDK 17+**, sử dụng `java.util.logging` mà không cần dependency bên ngoài. Để không phụ thuộc server/framework, nó **mô phỏng** một request HTTP bằng record `RequestContext`; trong ứng dụng thực, `requestId`, `method` và `route` được lấy từ middleware/router sau khi kiểm tra an toàn.

Một request có số lượng không hợp lệ sẽ trả `400`, đồng thời log `requestId`, `method`, `route`, `status`, `errorCode` và `Throwable`. Request hợp lệ trả `200`, không bị log nhầm là lỗi.

Lưu file **`RequestErrorContextDemo.java`**:

```java
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RequestErrorContextDemo {
    private static final Logger LOGGER =
            Logger.getLogger(RequestErrorContextDemo.class.getName());

    private record RequestContext(
            String requestId, String method, String route) {
    }

    private static ConsoleHandler configureLogging() {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                StringBuilder text = new StringBuilder()
                        .append(record.getLevel().getName())
                        .append(" | ")
                        .append(formatMessage(record))
                        .append(System.lineSeparator());

                if (record.getThrown() != null) {
                    StringWriter buffer = new StringWriter();
                    record.getThrown().printStackTrace(
                            new PrintWriter(buffer));
                    text.append(buffer);
                }
                return text.toString();
            }
        });

        LOGGER.addHandler(console);
        return console;
    }

    private static int handle(RequestContext request, int quantity) {
        try {
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            return 200;
        } catch (IllegalArgumentException error) {
            String message =
                    "event=http_request_failed"
                    + " requestId=" + request.requestId()
                    + " method=" + request.method()
                    + " route=" + request.route()
                    + " status=400"
                    + " errorCode=INVALID_QUANTITY";

            LOGGER.log(Level.WARNING, message, error);
            return 400;
        }
    }

    public static void main(String[] args) {
        ConsoleHandler console = configureLogging();
        try {
            RequestContext request =
                    new RequestContext("req-81", "POST", "/orders/{id}");

            System.out.println("invalidStatus=" + handle(request, -2));
            System.out.println("validStatus=" + handle(request, 3));
        } finally {
            LOGGER.removeHandler(console);
            console.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 RequestErrorContextDemo.java
java RequestErrorContextDemo
```

**Stdout chính xác:**

```text
invalidStatus=400
validStatus=200
```

**Stderr** có dòng mở đầu chính xác sau; những dòng stack trace phía sau chứa số dòng source nên chỉ minh họa:

```text
WARNING | event=http_request_failed requestId=req-81 method=POST route=/orders/{id} status=400 errorCode=INVALID_QUANTITY
java.lang.IllegalArgumentException: quantity must be positive
    at RequestErrorContextDemo.handle(RequestErrorContextDemo.java:...)
    at RequestErrorContextDemo.main(RequestErrorContextDemo.java:...)
```

JUL `ConsoleHandler` ghi ra **stderr**; nếu terminal gộp stdout và stderr thì thứ tự xen kẽ giữa các luồng không được đảm bảo tuyệt đối. Trong `handle`, exception được truyền trực tiếp qua `LOGGER.log(Level.WARNING, message, error)`, nên bản ghi giữ đối tượng `Throwable`. Formatter của demo gọi `printStackTrace` trên throwable để hiển thị chứng cứ lỗi. `printStackTrace` ở đây ghi vào **buffer do formatter quản lý**, không phải gọi trực tiếp từ mã nghiệp vụ để thay thế logging.

**Những lựa chọn có chủ đích trong demo:**

1. `RequestContext` là dữ liệu đã được mô phỏng và biết trước là an toàn. Khi tích hợp HTTP thật, đừng nối trực tiếp input không tin cậy vào message.
2. `route=/orders/{id}` là **mẫu tuyến**; không có ID khách hàng, query string hoặc token trong log.
3. `errorCode=INVALID_QUANTITY` là mã lỗi do ứng dụng quy định, không phải chuỗi lấy từ client.
4. `status=400` là kết quả mà hàm `handle` thực sự trả về; ví dụ không giả lập trường hợp response đã gửi rồi hoặc socket ngắt.
5. `LOGGER.setUseParentHandlers(false)` tránh thêm dòng từ handler cha để kết quả dễ kiểm chứng. Trong hệ thống thật, chỉ thay đổi propagation sau khi hiểu cấu hình logging chung.
6. Logger và handler trong ví dụ có mức `INFO`; sự kiện `WARNING` được chấp nhận. `ConsoleHandler` được tháo và đóng khi demo kết thúc.

Đây là chương trình dạy cơ chế **exception + request context**, không phải một HTTP server. Trong một server thật, thời gian xử lý, mã trạng thái thực gửi và thông tin route phải lấy từ pipeline của framework, chứ không được tự suy ra từ kiểu exception.

## 7. Đo duration và không nhầm thời gian xử lý

Duration là chỉ dấu hữu ích khi điều tra timeout hoặc hiệu năng. Trong Java, để đo khoảng thời gian trôi qua trong cùng tiến trình, thường dùng `System.nanoTime()`:

```java
// Fragment minh họa trong cùng một lời gọi xử lý request.
long started = System.nanoTime();
try {
    processRequest();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    long durationMs =
            java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
    // Đưa durationMs vào event tổng kết của request.
}
```

Đoạn này cần phương thức `processRequest()` của ứng dụng và không chạy độc lập. `System.nanoTime()` thích hợp để tính **khoảng thời gian**, không dùng giá trị đó làm timestamp hoặc so sánh tuyệt đối giữa tiến trình/máy khác nhau. Timestamp nên lấy từ đồng hồ thời gian thực kèm timezone, thường UTC, còn duration từ đồng hồ monotonic.

Đừng ghi `durationMs=0` như một giá trị giả khi hệ thống chưa đo thời gian. Nếu một request đang chạy hoặc đã bị hủy, cần phân biệt tình trạng với request xử lý xong; các mức thời gian có thể đo ở gateway, servlet filter và downstream sẽ không giống nhau vì mỗi tầng có phạm vi riêng.

## 8. Tự động bổ sung request ID bằng logging context

Với JUL thuần, một cách dễ học là **truyền dữ liệu ngữ cảnh một cách tường minh**, như record `RequestContext` của ví dụ. Logger JUL mặc định không cung cấp MDC giống SLF4J. Các framework thực tế thường có cơ chế request scope, tracing và context propagation riêng.

Trong dự án dùng **SLF4J với backend hỗ trợ MDC**, có thể đặt một ID đã tin cậy vào MDC cho thời gian xử lý:

```java
// Fragment trong dự án có SLF4J; requestId và processRequest() đã tồn tại.
org.slf4j.MDC.put("requestId", requestId);
try {
    processRequest();
} finally {
    org.slf4j.MDC.remove("requestId");
}
```

Đoạn này yêu cầu SLF4J API/provider phù hợp và không phải chương trình JDK thuần. Để `requestId` thực sự xuất hiện trong log, **encoder/layout của backend phải được cấu hình đọc trường MDC**; gọi `MDC.put` đơn thuần không đảm bảo message in ra chứa ID.

Ví dụ mẫu trong một file cấu hình Logback, khi ứng dụng đã dùng Logback:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level requestId=%X{requestId} %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Đây là **cấu hình Logback**, không dùng cho JUL hay Log4j 2 nguyên dạng. Thực tế cần quyết định timezone, cách hiển thị exception, định dạng JSON nếu collector cần, và cách kết hợp với cấu hình logging do framework cung cấp.

### Vì sao phải dọn MDC và truyền qua luồng bất đồng bộ?

Thread pool tái sử dụng luồng. Nếu gắn `requestId` vào MDC của luồng nhưng không `remove` hoặc `clear` trong `finally`, request sau có thể bị gán nhầm ID cũ. Tương tự, việc giao task sang executor, gọi `CompletableFuture` hoặc chuyển sang thread/reactive context **không tự bảo đảm** MDC được truyền và dọn đúng cách. Cần dùng cơ chế context propagation được framework/observability stack hỗ trợ.

Đối với một request đi qua nhiều service, có thể truyền correlation ID bằng một HTTP header đã được chuẩn hóa và kiểm tra; distributed tracing sử dụng cơ chế propagation riêng như Trace Context khi hệ thống đã áp dụng. Không lấy các giá trị header đầu vào làm chân lý nếu chưa xác lập ranh giới tin cậy.

## 9. Ghi exception ở dạng có cấu trúc

Một event có cấu trúc tách message tự do khỏi các trường có thể tìm kiếm. Ví dụ minh họa JSON:

```json
{
  "timestamp": "2026-11-09T10:15:30.125Z",
  "level": "ERROR",
  "event": "http_request_failed",
  "service": "order-service",
  "requestId": "req-81",
  "traceId": "trace-27",
  "method": "POST",
  "route": "/orders/{id}/reserve",
  "status": 500,
  "errorCode": "INVENTORY_RESERVE_FAILED",
  "durationMs": 128,
  "exceptionType": "java.lang.IllegalStateException",
  "message": "Cannot reserve inventory"
}
```

Đây là dữ liệu **giả định để học cấu trúc**, không phải output từ `RequestErrorContextDemo`. Hệ thống production có thể cần trường `stackTrace` hoặc trường lỗi chuẩn của backend để giữ đầy đủ chứng cứ. Với hệ thống thu thập log theo từng dòng, encoder có thể xuất **mỗi JSON object trên một dòng**, escape newline trong stack trace thay vì pretty-print nhiều dòng; cú pháp cụ thể phụ thuộc backend và phiên bản.

Lợi ích của structured logging là có thể truy vấn `requestId`, `errorCode`, `status`, `route` mà không phải đoán cấu trúc từ một câu văn. Không nên dùng cách **tự nối JSON bằng chuỗi** chứa input người dùng: hãy dùng serializer/encoder chính thức, đặt giá trị không tin cậy vào trường dữ liệu và xử lý ký tự điều khiển đúng cách.

Structured logging cũng không tự bảo đảm log bền vững hoặc không lộ thông tin. Vẫn cần quyền truy cập, chính sách retention, giới hạn kích thước, xử lý dữ liệu nhạy cảm và kiểm tra thu thập ở đích cuối.

## 10. Những tình huống điều tra cụ thể

### Tình huống A: lỗi đầu vào `400`

Log:

```text
WARNING event=http_request_failed requestId=req-81 method=POST route=/orders/{id} status=400 errorCode=INVALID_QUANTITY
```

Bằng chứng cho thấy request bị từ chối theo một quy tắc đầu vào. Nếu đây là tình huống dự kiến và thường xuyên, ứng dụng có thể không cần in stack trace cho mỗi lần từ chối. Người điều tra có thể lọc `errorCode=INVALID_QUANTITY` theo route để biết lỗi nằm ở quy tắc nào và có tăng bất thường hay không. Không cần log toàn bộ payload để biết số lượng không hợp lệ.

### Tình huống B: lỗi phụ thuộc sau retry

```text
WARN requestId=req-82 dependency=inventory-api attempt=1 outcome=retry reason=timeout
WARN requestId=req-82 dependency=inventory-api attempt=2 outcome=retry reason=timeout
ERROR event=http_request_failed requestId=req-82 route=/orders/{id}/reserve status=503 errorCode=UPSTREAM_TIMEOUT attempts=3
```

Đây là **log minh họa**. Hai dòng đầu là những lần thử chưa kết thúc; dòng cuối thể hiện request cuối cùng thất bại theo chính sách thử lại. Khi điều tra cần nối các log cùng `requestId`, kiểm tra thời điểm, tác động của timeout và dịch vụ phụ thuộc. Không nên đếm ba dòng là ba request lỗi độc lập.

### Tình huống C: ngoại lệ `500` bất ngờ

```text
ERROR event=http_request_failed requestId=req-83 method=GET route=/reports/{id} status=500 errorCode=UNEXPECTED_ERROR
java.lang.NullPointerException: ...
```

Cần log đầy đủ stack trace/cause để tìm lỗi thực sự; `requestId` cho phép xem các log trước đó của request. Response cho client nên có mã lỗi chung và ID tham chiếu, không trả chi tiết stack trace. Không kết luận nguyên nhân chỉ bằng việc thấy `NullPointerException`; phải xác định đối tượng nào rỗng và vì sao tiền điều kiện bị vi phạm.

## 11. Các lỗi thiết kế khi log request lúc exception

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ log `exception.getMessage()` | Không biết request và mất stack trace/cause | Log errorCode, requestId, route, status và `Throwable` ở ranh giới phù hợp |
| Log nguyên URL kèm query string | Có thể lộ token, email, nội dung tìm kiếm | Ưu tiên route template, che các trường nhạy cảm |
| Log toàn bộ headers/body | Rò rỉ credentials, thông tin cá nhân, payload lớn | Chỉ chọn trường thật sự cần, theo allowlist |
| Tin trực tiếp `X-Forwarded-For` hoặc correlation ID từ client | Giả mạo nguồn/định danh, log injection | Kiểm tra/chuẩn hóa qua trusted gateway |
| Log cùng exception ở repository, service và controller | Stack trace trùng, khó biết số lỗi thật | Quy ước một điểm log đầy đủ ở request boundary |
| `requestId` chỉ có trên dòng lỗi, không có ở bước trước | Không kết nối được diễn tiến request | Truyền và ghi ID ở các sự kiện quan trọng |
| Quên dọn MDC khi dùng thread pool | Request mới mang ngữ cảnh của request cũ | `finally` và context propagation đúng |
| Ghi `status=200` trước khi biết kết quả thực | Log mâu thuẫn response | Ghi status thực hoặc phân biệt trạng thái dự kiến |
| Coi mọi `4xx` là lỗi hệ thống nghiêm trọng | Nhiễu cảnh báo, bỏ qua lỗi `5xx` đáng xử lý | Chọn level theo tác động và phân loại lỗi |
| Ghi raw input có CR/LF | Có thể giả mạo dòng log hoặc phá parser | Escape, giới hạn độ dài và structured encoder |
| Dùng `System.out.println`/ `printStackTrace()` thay log exception | Mất level, category, correlation và cấu hình lưu trữ | Dùng logging API với `Throwable` |
| Ghi quá nhiều dữ liệu khi exception | Tăng độ trễ, dung lượng, nguy cơ lộ dữ liệu | Dùng mã lỗi và metadata tối thiểu nhưng đủ điều tra |

**Bảo mật log:** Dữ liệu từ request là đầu vào không tin cậy. Ngoài việc lọc bí mật, cần xử lý ký tự điều khiển và giới hạn chiều dài để tránh log forging, làm hỏng parser hoặc tạo chi phí quá lớn. Không giả định mọi `toString()` của đối tượng request đều an toàn; một số phương thức có thể bao gồm trường nhạy cảm.

## 12. Checklist triển khai

Khi thiết kế exception logging cho HTTP request, hãy tự kiểm tra:

1. **Định danh:** request có `requestId` đáng tin cậy; `traceId`/`spanId` nếu dự án có tracing; các sự kiện cùng request được liên kết.
2. **Đúng chức năng:** có `method`, route template và thành phần xử lý; tránh full URL/query nhạy cảm.
3. **Đúng kết quả:** có `errorCode` ổn định, HTTP status đã được quyết định/ghi nhận, outcome và duration nếu có đo.
4. **Đúng lỗi kỹ thuật:** giữ `Throwable`, stack trace và chuỗi `Caused by` cho những lỗi cần chẩn đoán; không ghi trùng vô ích.
5. **Đúng mức độ:** lỗi đầu vào dự kiến và lỗi hệ thống không bị đánh đồng; chính sách log phù hợp khối lượng request.
6. **An toàn dữ liệu:** header, body, IP, path parameter và thông tin người dùng được đánh giá trước khi log; không lộ token/mật khẩu.
7. **An toàn ngữ cảnh:** request context được truyền đúng qua async/executor và được dọn sau khi xử lý; không lẫn ID giữa các request.
8. **Dễ vận hành:** formatter/encoder giữ tên trường ổn định; hệ thống thu thập có thể tìm đúng request và exception.
9. **Kiểm chứng:** thử một request thành công, một lỗi `4xx`, một lỗi `5xx` và tình huống retry/timeout; đối chiếu log với response.
10. **Tài nguyên:** có giới hạn dung lượng, thời gian lưu và quyền truy cập phù hợp với loại dữ liệu đã được phép ghi.

**Kết quả cần đạt:** Từ một event exception, người điều tra xác định được **request nào thất bại, thao tác gì, ở thành phần nào, trả kết quả gì, và cần tìm các dấu vết liên quan ở đâu**. Request context được chọn lọc giúp việc điều tra nhanh và chính xác hơn, đồng thời tránh biến hệ thống logging thành nơi lưu trữ dữ liệu HTTP nhạy cảm.
