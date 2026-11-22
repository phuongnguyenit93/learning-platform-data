# Request body và rủi ro khi logging trong ứng dụng web Java

## 1. Mục tiêu và vấn đề thực tế

Trong ứng dụng web, **request body** là phần dữ liệu được client gửi kèm HTTP request, chẳng hạn JSON tạo đơn hàng, form đăng nhập, nội dung webhook, file upload hoặc dữ liệu nhị phân. Body có thể giúp tái hiện lỗi, nhưng **ghi nguyên request body vào log** là một quyết định rủi ro cao: có thể lộ mật khẩu, access token, dữ liệu cá nhân, thông tin thanh toán, nội dung riêng tư, hoặc làm cạn bộ nhớ/I/O và phá vỡ cơ chế xử lý stream.

Ví dụ nguy hiểm:

```java
// Mã minh họa trong ứng dụng có logger và biến requestBody.
// KHÔNG dùng trong production nếu body chưa được phân loại an toàn.
logger.debug("Incoming body={}", requestBody);
```

Khi DEBUG được bật, log có thể nhận cả thông tin người dùng gửi. Khi DEBUG tắt, phép tạo `requestBody` hoặc `toJson(request)` **vẫn có thể đã chạy** trước khi gọi logger. Nếu dữ liệu được gửi sang nhiều sink (console, file, hệ thống tập trung, alert, backup), phạm vi rò rỉ lớn hơn một file cục bộ.

**Nguyên tắc cốt lõi:** thông thường **không log raw request body**. Hãy log những **metadata và field được cho phép** như method, route template, status, duration, request ID do hệ thống kiểm soát, body size đã đo, mã lỗi hoặc action nghiệp vụ. Nếu trường hợp điều tra thực sự cần nội dung, hãy dùng một cơ chế thu thập riêng, có phạm vi hẹp, redaction theo cấu trúc, giới hạn dung lượng và quyền truy cập.

Sau bài này, bạn sẽ hiểu:
- Body có thể chứa những loại dữ liệu nhạy cảm nào và vì sao level DEBUG không phải biện pháp bảo vệ.
- Những tác động đến **stream, bộ nhớ, CPU, I/O, latency, DoS và hoạt động async** khi cố đọc/log body.
- Cách ghi log request an toàn trong Java 17, Spring MVC/Servlet, và lưu ý cho WebFlux/streaming.
- Vai trò của allowlist, masking, redaction, size limit, consent, retention và fault isolation.
- Cách kiểm thử để chắc body thực sự không bị ghi qua appender, exception, proxy hoặc collector.

## 2. Request body là gì, và khác headers/query như thế nào?

Một HTTP request minh họa:

```http
POST /api/sessions HTTP/1.1
Host: example.test
Content-Type: application/json
Content-Length: 54

{"username":"alice","password":"demo-secret"}
```

Body ở đây là JSON chứa `username` và `password`. Các giá trị là **dữ liệu giả** để minh họa rủi ro. Trong hệ thống thật, ứng dụng có thể nhận:
- `application/json`: object, array, nested fields, danh sách dài.
- `application/x-www-form-urlencoded`: các cặp key-value, thường gồm credential hoặc token.
- `multipart/form-data`: form fields cộng file upload.
- `text/plain`, XML, CSV, protobuf hoặc loại dữ liệu tùy chỉnh.
- Body từ webhook, API call, GraphQL (query/variables), gRPC qua giao thức tương ứng, hoặc streaming upload.

**Không phải request nào cũng có body.** Một GET thường không cần body; một request có thể khai báo `Content-Length: 0` hoặc truyền theo kiểu chunked. `Content-Type` chỉ là thông tin về loại biểu diễn, không chứng minh nội dung an toàn. Một JSON với tên field “debug” vẫn có thể chứa token; một file text có thể chứa dữ liệu cá nhân.

Một số rủi ro có thể đến từ **headers và URL query** thay vì body; chúng cần chính sách riêng. Ví dụ `Authorization`, `Cookie`, signed URL và query token không nằm trong body nhưng cũng không được ghi bừa bãi. Bài này tập trung vào **body** và tương tác với logging pipeline, song không được bỏ qua các kênh rò rỉ song song.

## 3. Ma trận rủi ro khi ghi raw request body

| Nhóm rủi ro | Ví dụ cụ thể | Hậu quả |
| --- | --- | --- |
| **Bí mật xác thực** | Password, OTP, refresh token, API key, session secret, private key | Chiếm tài khoản/truy cập dịch vụ nếu giá trị còn hiệu lực |
| **Dữ liệu cá nhân** | Email, địa chỉ, hồ sơ, số giấy tờ, thông tin sức khỏe | Lộ đời tư, vượt mục đích xử lý, vi phạm chính sách |
| **Thông tin thanh toán** | Dữ liệu thẻ, tài khoản ngân hàng, chi tiết thanh toán | Gia tăng rủi ro gian lận và tuân thủ |
| **Nội dung riêng tư** | Tin nhắn, tài liệu, mã nguồn gửi lên, file đính kèm | Lộ dữ liệu khách hàng/kinh doanh |
| **Chi phí hệ thống** | Body lớn, nested JSON, Base64, file nhiều GB | Allocation/GC, CPU serialize, băng thông, log storage tăng |
| **Phá stream** | Filter đọc `getInputStream()` trước controller | Controller không còn dữ liệu để deserialize |
| **Log injection** | Nội dung chứa newline, ký tự điều khiển/escape | Tạo log giả, phá parser, che dấu sự kiện |
| **Chặn nghiệp vụ** | Logger/encoder/file/network sink chậm | Tăng p95/p99, giữ thread, timeout |
| **Nhân bản dữ liệu** | Console + rolling file + collector + backup | Dữ liệu nhạy cảm có thêm bản sao và người có quyền đọc |
| **Sai mô hình bảo mật** | Chỉ redact trên dashboard nhưng raw file còn nguyên | Cảm giác an toàn giả, vẫn lộ ở upstream |

**Body là dữ liệu không tin cậy do client cung cấp.** Không chỉ cần tránh lộ bí mật; còn phải tránh để client quyết định kích thước, số dòng, cấu trúc hoặc nội dung trường log theo cách ảnh hưởng đến hoạt động hệ thống.

## 4. Vì sao DEBUG/TRACE không bảo vệ được dữ liệu?

Nhiều dự án ghi payload ở DEBUG với kỳ vọng chỉ bật trong test:

```java
// Mã tích hợp minh họa, không phải khuyến nghị.
logger.debug("Request: " + toJson(requestDto));
logger.trace("Payload: {}", requestDto);
```

Vấn đề:
1. **Level là cấu hình runtime.** Một operator có thể bật DEBUG/TRACE khi điều tra sự cố; log cũ hoặc luồng khác có thể vẫn bật level chi tiết.
2. **Đối số có thể được tính trước.** `toJson(requestDto)` và phép nối chuỗi ở dòng đầu đã chạy ngay khi thực thi. Dù event bị từ chối, hiệu năng vẫn bị ảnh hưởng.
3. **Parameterized logging không che dữ liệu.** `{}` chỉ kiểm soát cách format, không tự redact `requestDto`.
4. **`toString()` của DTO/record/entity có thể chứa mọi field**, kể cả password. Một số generator/Lombok/record sinh ra biểu diễn object không phù hợp để log.
5. **Sink và collector có thể lưu bản sao**, dù ở UI dashboard đã ẩn hoặc giới hạn quyền.
6. **Exception path** có thể log request theo cách khác, ngay cả khi lời gọi DEBUG bình thường đã bị xóa.

Khi cần chẩn đoán, hãy **chủ động chọn field an toàn** và dùng event code/trace ID. Không nên định nghĩa tính an toàn bằng “chỉ khi bật DEBUG”.

## 5. Đọc request body có thể làm hỏng luồng xử lý HTTP

### 5.1. Body thường đi qua một input stream

Trong Servlet API, controller hoặc framework có thể gọi `request.getInputStream()` hoặc `request.getReader()` để nhận bytes/chars. Body thông thường được đọc theo luồng; nó **không phải một String vô hạn có thể đọc lại tùy ý**.

Một filter viết theo kiểu sau dễ làm downstream không còn body:

```java
// CHỈ LÀ VÍ DỤ PHẢN DIỆN; yêu cầu Jakarta Servlet.
// Việc đọc stream để ghi log có thể làm controller không còn dữ liệu.
byte[] raw = request.getInputStream().readAllBytes();
logger.debug("Body={}", new String(raw, java.nio.charset.StandardCharsets.UTF_8));
chain.doFilter(request, response);
```

Đây là **đoạn code không nên dùng** vì:
- `readAllBytes()` có thể đọc toàn bộ payload vào heap, không giới hạn kích thước.
- Stream đã bị tiêu thụ; framework phía sau có thể gặp empty body, lỗi deserialize hoặc hành vi khác.
- `new String(raw, UTF_8)` không phù hợp với binary body, charset khác và multipart.
- Raw body có thể chứa credential/PII; log làm lộ nội dung.
- Nếu đối tượng request là wrapper hoặc container áp chế độ đọc đặc biệt, hành vi còn phụ thuộc cách triển khai.

**Không thêm một lần đọc body chỉ để phục vụ log.** Nếu business logic đã phải deserialize body, lấy metadata hoặc các field đã được phê duyệt **từ kết quả xử lý nghiệp vụ**. Nếu cần đo kích thước, dùng streaming byte counter có giới hạn và tôn trọng flow của framework thay vì clone toàn bộ payload.

### 5.2. Content-Length không phải số bytes đã nhận thực tế

`request.getContentLengthLong()` trong Servlet trả về giá trị độ dài được khai báo/được container biết, hoặc `-1` nếu không xác định được. Nó có thể không đại diện cho số bytes ứng dụng thực sự tiêu thụ, nhất là khi truyền chunked, bị cắt giữa chừng, được giải nén hoặc đi qua middleware.

Nếu log `body_bytes`, hãy ghi rõ nguồn:
- `declared_content_length`: độ dài được khai báo/quan sát từ metadata; có thể là `-1` hoặc không tin cậy hoàn toàn.
- `received_body_bytes`: số bytes thực tế được một thành phần streaming counter tin cậy đếm khi xử lý.
- `decoded_body_bytes`: số bytes sau decompress/biến đổi nếu framework có bước này.

Không tự đọc stream thêm lần nữa để đo. Phân biệt kích thước byte với `String.length()`: trong Java, `String.length()` đếm các đơn vị UTF-16, không phải số bytes truyền qua HTTP.

### 5.3. Body có thể chỉ đọc một phần hoặc chưa được đọc

Khi request bị từ chối sớm (authentication, authorization, rate limit, validation trên header), ứng dụng có thể **không đọc body**. Một logger chạy ở cuối filter chain không nên cho rằng có thể tái tạo body đầy đủ. Việc cố đọc nốt để “ghi cho đủ” còn làm tăng chi phí không cần thiết và dễ kéo dài xử lý một request độc hại.

Đối với lỗi client đóng kết nối giữa chừng, body có thể chỉ được nhận một phần. Audit nên phản ánh chính xác **received/consumed** khi có dữ liệu đo thực, không suy đoán đã nhận đầy đủ chỉ từ Content-Length.

## 6. Ví dụ Java 17 độc lập: chỉ ghi metadata, không ghi payload

Ví dụ thuần JDK 17 dưới đây giả lập một HTTP body JSON chứa password và access token **giả**. Ứng dụng đã nhận bytes đó để xử lý nghiệp vụ; chức năng logging **không đọc thêm, không deserialize lại và không ghi body**. Thay vào đó, log một sự kiện có method, route template, status, request ID và độ dài đã biết.

Tạo file `SafeRequestBodyLoggingDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class SafeRequestBodyLoggingDemo {
    private static final class CaptureHandler extends Handler {
        private final StringBuilder captured = new StringBuilder();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                captured.append(record.getMessage()).append('\n');
            }
        }

        @Override
        public void flush() {
            // Chỉ giữ log trong bộ nhớ của demo.
        }

        @Override
        public void close() {
            flush();
        }

        String text() {
            return captured.toString();
        }
    }

    private static void logRequest(
            Logger logger, String method, String route,
            String requestId, int status, long receivedBytes) {
        // Các trường đều do ứng dụng kiểm soát/chuẩn hóa; KHÔNG có raw body.
        logger.info("event=http_request"
                + " method=" + method
                + " route=" + route
                + " requestId=" + requestId
                + " status=" + status
                + " receivedBytes=" + receivedBytes
                + " bodyLogged=false");
    }

    public static void main(String[] args) {
        String body =
                "{\"password\":\"fake-pass\",\"access_token\":\"fake-token\"}";
        byte[] requestBytes = body.getBytes(StandardCharsets.UTF_8);

        Logger logger = Logger.getLogger("lesson.web.body.safe");
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);

        CaptureHandler handler = new CaptureHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        try {
            // Ví dụ dùng số byte đã có từ quá trình nhận/xử lý body.
            logRequest(logger, "POST", "/sessions", "req-42",
                    401, requestBytes.length);

            String emittedLog = handler.text();
            System.out.print(emittedLog);

            boolean secretLeaked = emittedLog.contains("fake-pass")
                    || emittedLog.contains("fake-token");
            System.out.println("secretLeaked=" + secretLeaked);
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac SafeRequestBodyLoggingDemo.java
java SafeRequestBodyLoggingDemo
```

**Stdout chính xác** trên JDK 17, trong JVM mới không có thành phần khác can thiệp logger demo:

```text
event=http_request method=POST route=/sessions requestId=req-42 status=401 receivedBytes=52 bodyLogged=false
secretLeaked=false
```

Phân tích:
1. JSON payload chứa hai giá trị bí mật **giả lập**, chỉ để minh họa. Vì các ký tự trong chuỗi JSON đều là ASCII, `requestBytes.length=52`; trong trường hợp Unicode, phải đo bằng bytes thực chứ không lấy `body.length()`.
2. `logRequest` nhận một số đo bytes và các metadata do ứng dụng kiểm soát. Nó **không nhận nguyên body** nên không thể vô tình gọi `toString()` hoặc serialize lại object có credential.
3. `CaptureHandler` chỉ giữ thông điệp để assert, không tự thêm timestamp hoặc xuất stderr; `setUseParentHandlers(false)` ngăn root handler ghi bản thứ hai.
4. `secretLeaked=false` chứng minh **chỉ log do ví dụ tạo** không chứa hai chuỗi giả. Nó **không phải phép chứng minh toàn bộ ứng dụng, HTTP server, gateway và collector đều không ghi body**.
5. Mã dùng một thread để minh họa; `StringBuilder` trong handler không thread-safe cho một ứng dụng logging đồng thời. Trong production, dùng backend và lifecycle do framework quản lý.

**Lưu ý:** Có body bytes trong code là vì nghiệp vụ đã nhận body. Đoạn ví dụ **không khuyên đọc `getInputStream()` để lấy bytes chỉ nhằm log**. API logging trong thực tế nên nhận DTO/sự kiện đã chuẩn hóa, không nhận raw request.

## 7. Cách thiết kế log request: allowlist trước, redaction sau

Một log request hữu ích thường không cần nội dung body. Ví dụ:

```json
{
  "event": "http_request",
  "method": "POST",
  "route": "/orders",
  "status": 201,
  "duration_ms": 38,
  "request_id": "req-42",
  "received_body_bytes": 284,
  "body_logged": false
}
```

Đây là **dữ liệu minh họa**, không phải kết quả quan sát trong hệ thống thật. Schema thực tế cần quyết định rõ:
- `method`: HTTP method được framework kiểm tra/canonicalize.
- `route`: **route template** (`/orders/{id}`), tránh dùng raw URL có ID/secret ở path/query.
- `status` và `duration_ms`: đo từ quá trình xử lý thực tế.
- `request_id`: do server sinh hoặc được validate/giới hạn độ dài; không tin vô điều kiện một header do client gửi.
- `received_body_bytes`: chỉ dùng khi có bộ đếm thực tế; nếu không có, có thể bỏ hoặc dùng `declared_content_length` với tên chính xác.
- `body_logged`: thể hiện chính sách ghi ở điểm đó, không phải tuyên bố các thành phần khác chưa ghi body.
- `event_code`, `validation_error_code`, `resource_type`: chọn mã lỗi/loại nghiệp vụ **không chứa input tự do**.

**Allowlist** nghĩa là định nghĩa cụ thể trường được phép rồi mới tạo event. Trái lại, blacklist cố loại vài field nhạy cảm khỏi toàn bộ JSON thường bỏ sót field mới, JSON lồng sâu, mảng, alias, token trong string, hoặc dữ liệu được encode theo cách khác.

Với sự kiện nghiệp vụ, thay vì log toàn bộ DTO:

```java
// Đoạn tích hợp SLF4J. orderId/status đã được kiểm tra,
// không phải credential hoặc dữ liệu cá nhân nhạy cảm.
logger.info("event=order_created orderId={} status={} itemCount={}",
        orderId, "CREATED", itemCount);
```

Nếu `orderId` có thể xác định người dùng hoặc đơn hàng nhạy cảm, hãy áp chính sách truy cập/retention tương ứng. **Không phải mọi ID đều vô hại**. Với endpoint đăng nhập, có thể log mã sự kiện `LOGIN_DENIED` và lý do chuẩn hóa mà không cần username/password.

## 8. Spring MVC/Servlet: gắn log tại đâu?

### 8.1. Filter/interceptor không cần đọc body để ghi metadata

Trong Spring MVC hoặc Servlet application, filter có thể quan sát method và status; route template sau khi handler mapping chạy có thể lấy từ thông tin của framework khi sẵn có. Đây là **mảnh code tích hợp** minh họa Spring Web MVC/Jakarta Servlet, không phải một class độc lập:

```java
// Bên trong Servlet Filter, sau chain.doFilter(request, response).
// HandlerMapping thuộc spring-webmvc; có thể không có attribute nếu chưa match.
Object matchedRoute = request.getAttribute(
        org.springframework.web.servlet.HandlerMapping
                .BEST_MATCHING_PATTERN_ATTRIBUTE);

String route = matchedRoute instanceof String s ? s : "UNMATCHED";
long declaredLength = request.getContentLengthLong();

logger.info("event=http_request method={} route={} status={} "
                + "declaredContentLength={} bodyLogged=false",
        request.getMethod(), route, response.getStatus(), declaredLength);
```

Lưu ý quan trọng:
- `declaredContentLength` **không chắc là số bytes đã nhận**; `-1` nghĩa là không biết.
- `UNMATCHED` có thể xảy ra nếu request bị chặn trước khi vào controller hoặc không có mapping; đừng thay bằng raw URL/query chỉ để “cho đủ”.
- Nếu filter log cả request chưa xác thực, phải coi các field từ client là dữ liệu không tin cậy và sanitize/limit trước khi ghi.
- Nếu chỉ cần method/route/status, **không cần** `ContentCachingRequestWrapper` và không cần đọc `getInputStream()`.
- Đặt log trong `finally` thích hợp khi cần ghi cả đường xử lý exception, nhưng phải xác định cách status/exception được chuyển bởi exception handler và servlet container; status lúc filter trở về không phải lúc nào cũng phản ánh response cuối đã gửi.
- Nếu sử dụng asynchronous Servlet processing, việc filter chain trả về có thể xảy ra trước khi request thực sự hoàn tất; hãy gắn instrumentation vào lifecycle phù hợp (`AsyncListener` hoặc cơ chế framework) để đo duration/outcome cuối.

### 8.2. ContentCachingRequestWrapper không phải công cụ “đọc body vô hại”

Spring Web cung cấp `ContentCachingRequestWrapper` để giữ bản sao **những bytes đã được tiêu thụ qua wrapper**, có giới hạn cache. Nó hữu ích trong một số integration có kiểm soát, nhưng:

1. **Wrapper không tự đọc toàn bộ body ngay khi khởi tạo.** `getContentAsByteArray()` có thể rỗng nếu downstream chưa đọc hoặc chỉ chứa phần đã đọc.
2. Cache có thể có **giới hạn** và chỉ chứa một phần body. Vì vậy không nên coi cache là bản sao đầy đủ của payload.
3. Nếu một filter tự đọc stream sớm, **downstream có thể không đọc lại được** theo cách ứng dụng mong đợi. Đừng giả định việc bọc bằng wrapper tự động biến request thành repeatable request cho mọi trường hợp.
4. Cache làm **tăng lượng bytes trong heap**. Nếu cache limit là 8 KiB nhưng traffic rất cao và nhiều request đồng thời, tổng memory vẫn đáng kể; request lớn và body binary cần đánh giá riêng.
5. Cache là một bản sao dữ liệu nhạy cảm, có thể nằm trong heap dump/tracing và dễ bị ghi raw ở một code path khác.
6. Multipart, form parsing, async dispatch và error paths có hành vi riêng; phải kiểm thử theo stack/phiên bản thực tế.

Nếu không có nhu cầu nghiệp vụ hợp lệ phải cache, **đừng thêm wrapper chỉ để log body**. Nếu có yêu cầu diagnostic đặc biệt, cần xác định rõ endpoint, data classification, giới hạn, masking theo cấu trúc và cách xóa/giảm vòng đời bản sao.

### 8.3. RequestBodyAdvice và DTO

Spring MVC có các điểm hook quanh việc đọc/convert body như `RequestBodyAdvice`. Chúng có thể nhìn thấy dữ liệu đã parse thành DTO (tùy converter và controller), giúp chọn **trường nghiệp vụ cụ thể được phép** thay vì sao chép raw bytes.

Tuy nhiên, việc hook thấy DTO **không khiến DTO tự an toàn**. Ghi `dto.toString()` hoặc serialize cả DTO vẫn có thể làm lộ token/password. Nên viết mapping sang `AuditView`/event schema chỉ chứa field được phép, hoặc phát event từ logic nghiệp vụ sau validation.

Đối với lỗi JSON parse xảy ra trước controller, không dựa vào raw exception message để tái tạo body. Ghi mã lỗi, vị trí/loại vấn đề khi được xem là an toàn, một request ID và số đo phù hợp; tránh log toàn bộ body vào exception hoặc debug diagnostics.

## 9. Reactive WebFlux, streaming và file upload

### 9.1. Body của WebFlux là luồng bất đồng bộ

Với Spring WebFlux/Reactor, body thường được biểu diễn bằng publisher và `DataBuffer`. Nếu một logging filter subscribe vào body chỉ để nhìn dữ liệu, nó có thể **tiêu thụ stream**, gây lỗi ở subscriber xử lý thật hoặc làm thay đổi backpressure. Việc gom body bằng `DataBufferUtils.join` có thể làm bộ nhớ tăng theo kích thước payload; quản lý buffer sai cách còn có thể gây leak trong một số cấu hình pooled buffers.

Không nên:
- Subscribe riêng một lần vào body trong logging filter.
- `collectList()` hoặc join toàn bộ upload lớn để in log.
- Giữ `DataBuffer` ngoài vòng đời hợp lệ hoặc quên release theo contract.
- Dùng `block()` trên luồng event loop chỉ để ghi log.

Nếu cần đo bytes, áp dụng một decorator/metrics hook **không làm thay đổi consumption/backpressure**, giới hạn tài nguyên và tuân thủ lifecycle `DataBuffer` của stack đang dùng. Nếu mục tiêu chỉ là log method, route, status, duration và trace ID, hãy làm ở observation/filter layer mà không thao tác vào body.

### 9.2. Multipart và binary body

`multipart/form-data` có thể chứa field text **và** file nhị phân. In raw multipart khiến log chứa tên file, nội dung upload, boundary, form field nhạy cảm hoặc nhiều MB/GB dữ liệu.

Nên ghi metadata khi được phép:
- Tên trường đã allowlist, không phải mọi field.
- Số lượng file, size đã đo, media type đã validate, result code.
- ID tham chiếu của đối tượng đã lưu, nếu không gây lộ thông tin cá nhân.
- Không mặc định ghi tên file do client gửi: nó có thể chứa path, email/PII hoặc ký tự điều khiển.
- Không lấy nội dung bytes hoặc đoạn đầu file để làm “preview log”.

Các dạng protobuf, PDF, image, ZIP và body đã nén không nên chuyển bừa sang String. `Content-Encoding: gzip` còn làm số bytes truyền khác số bytes sau giải nén. Nếu body giải nén lớn hơn nhiều so với dữ liệu truyền, cả bước deserialize và logging phụ đều có thể bị lợi dụng làm tăng tiêu thụ tài nguyên.

### 9.3. GraphQL và webhook

- **GraphQL:** body JSON thường chứa `query`, `operationName` và `variables`. Variables có thể là password, token hoặc dữ liệu riêng tư. Có thể log tên operation được kiểm tra và mã lỗi; không mặc định log toàn bộ query/variables.
- **Webhook:** body có thể chứa dữ liệu khách hàng, chữ ký hoặc event payload riêng tư. Nếu cần xác minh HMAC signature, xử lý bytes theo contract tại boundary; **không đưa raw body/signing secret vào log**. Khi cần chẩn đoán, log provider ID, event type đã validate và kết quả xác minh chữ ký.
- **Large streaming request:** ưu tiên counters và trạng thái nhận/validate hơn body snapshot. Không giữ toàn bộ stream để phục vụ một event logging.

## 10. Redaction và masking: đặt ở đâu và kiểm soát thế nào?

### 10.1. Những giải pháp có vẻ tiện nhưng chưa đủ

Ví dụ log body rồi thay chuỗi theo regex:

```java
// Mã phản diện minh họa. Đây KHÔNG phải bộ redactor đáng tin.
String safe = body.replaceAll(
        "\"password\"\\s*:\\s*\"[^\"]*\"",
        "\"password\":\"[REDACTED]\"");
logger.debug("body={}", safe);
```

Rủi ro:
- Cú pháp JSON có nesting, escape, unicode escape, mảng và nhiều cách biểu diễn. Regex đơn giản có thể bỏ sót.
- Field nhạy cảm có thể có tên khác: `pwd`, `credentials`, `token`, `secret`, `auth`, hoặc nằm trong string/URL.
- Body có thể không phải JSON, chứa binary, multipart hoặc XML.
- Regex và việc tạo bản sao body vẫn tốn CPU/heap.
- Một lỗi cấu hình hoặc exception có thể vô tình log **`body` trước khi redaction**.
- Redaction chỉ trên message text có thể bỏ qua fields cấu trúc, MDC, exception và appender khác.

Tốt hơn: **không đưa raw body vào logging API**. Với nội dung thật sự cần quan sát, parse bằng parser an toàn theo media type (đã có trong nghiệp vụ), chỉ xuất trường allowlist và chuyển dữ liệu qua một `SafeLogView`/DTO riêng.

### 10.2. Redaction theo cấu trúc

Giả sử DTO của yêu cầu đăng ký gồm `email`, `password`, `phone` và `campaignCode`. Nếu chỉ cần kiểm tra nguồn chiến dịch, một audit view có thể là:

```json
{
  "event": "signup_attempt",
  "campaign_code": "CAMPAIGN_PUBLIC",
  "validation_result": "DENIED",
  "body_logged": false
}
```

Đừng đưa email/password/phone vào log rồi mới mask nếu không cần. `campaign_code` cũng phải được giới hạn và validate, vì một trường tưởng là mã chiến dịch vẫn có thể nhận giá trị tùy ý từ client. Field bí mật cần **được bỏ** khỏi schema thay vì chỉ hiển thị `[REDACTED]` một cách máy móc.

### 10.3. Redaction ở appender/collector là defense in depth

Trong Logback hoặc Log4j 2, có thể có layout/encoder hoặc custom converter/filter để mask dữ liệu. Chúng hữu ích khi một thành phần vô tình tạo message không an toàn, nhưng:
- Appender A và appender B có thể dùng **encoder khác nhau**; phải kiểm tra từng đích.
- Raw event có thể nằm trong async queue/heap trước encoder.
- Stack trace, argument array, MDC, marker và key-value fields có thể cần xử lý riêng.
- Collector có thể giữ raw data trước bước index/redact.
- Log đã được chuyển tới console trước khi masked ở dashboard vẫn có thể tồn tại ở runtime log.

Do đó, hãy xem redaction tầng sau là **lớp bảo vệ thứ hai**, không phải chính sách để “được phép log mọi body”.

## 11. Giới hạn dữ liệu, chi phí và khả năng chống DoS

### 11.1. Vì sao một snapshot “nhỏ” vẫn có thể gây hại?

Giả sử mỗi request snapshot tối đa 8 KiB. Với nhiều request đồng thời, dữ liệu được giữ thêm trong heap có thể trở thành vài MB hoặc nhiều hơn, chưa kể copies khi chuyển byte[] thành String, formatter, JSON encoder, queue entry và network buffer. Nếu capture rồi log cả bản body trước khi cắt, giới hạn ở cuối không ngăn được allocation ban đầu.

**Giới hạn size chỉ là điều kiện về tài nguyên, không phải biện pháp chống lộ bí mật.** Một access token ngắn có thể nằm ngay trong 100 bytes đầu tiên. Không bao giờ khẳng định “chỉ log 1 KiB đầu” là an toàn.

### 11.2. Các giới hạn nên đặt

| Giới hạn | Mục đích |
| --- | --- |
| Max request body size ở ingress/server | Chặn payload quá lớn trước khi xử lý |
| Max decoded/decompressed size | Ngăn decompression bomb |
| Max JSON nesting depth / collection count | Ngăn payload có cấu trúc gây tốn parse/CPU |
| Max string/field length trong log | Tránh một giá trị phá log stream hoặc index |
| Max diagnostic snapshot khi có ngoại lệ hợp lệ | Giới hạn bộ nhớ/bytes, **sau khi** dữ liệu đã được phân loại và xử lý an toàn |
| Logging queue size | Kiểm soát memory/backpressure/drop |
| Rate limit và sampling có chủ đích | Giảm log storm, nhưng không dùng để bỏ audit bắt buộc |
| Retention, quota, rotation | Kiểm soát storage và vòng đời dữ liệu |

Khi áp dụng sampling, đặc biệt với lỗi xác thực hoặc hành vi an ninh, cần cân bằng giữa bảo toàn tín hiệu điều tra và khả năng vận hành. Sampling không thay thế việc chặn secret: một log bị lấy mẫu vẫn có thể làm lộ dữ liệu.

### 11.3. Async appender không xóa rủi ro

Async logging có thể làm business thread ít phải chờ file/network, nhưng:
- Eager `toJson(body)` đã chạy ở caller trước khi enqueue.
- Event có thể giữ references hoặc snapshot của body trong heap.
- Queue đầy có thể khiến producer block, drop event hoặc tăng độ trễ.
- Encoder ở worker vẫn cần CPU/heap để serialize.
- Shutdown/crash có thể để mất event chưa flush; file/collector vẫn có thể lưu secret nếu được gửi.

Cần đo end-to-end: CPU, GC, allocated bytes, p95/p99 latency, queue depth, dropped log events, bytes logged, chi phí collector và thời gian flush khi shutdown.

## 12. Lỗi, exception và thông tin body bị lộ gián tiếp

Thậm chí khi controller không gọi `logger.debug("body")`, body có thể lọt vào log qua:

1. **Validation errors**: exception message chứa raw rejected value của field.
2. **JSON parsing errors**: thư viện hoặc custom error wrapper chèn đoạn payload gần vị trí lỗi.
3. **HTTP client diagnostics**: ghi raw outbound request body hoặc response body khi retry/timeout.
4. **Framework debug/wire logs**: interceptor, filter, gateway hoặc proxy log request bodies nếu cấu hình bật.
5. **Custom exception**: `throw new IllegalArgumentException("Bad payload: " + rawBody)`.
6. **AOP/tracing**: tự log tham số controller method, trong đó có `@RequestBody` DTO.
7. **`toString()`/record/Lombok**: một dòng log cả object làm lộ mọi trường.
8. **Security audit**: ghi raw login payload, OTP hoặc token để điều tra thất bại.
9. **MDC/ThreadContext**: lưu body vào context, rồi encoder tự thêm vào mọi event.
10. **Error pages/incident tickets**: copy/paste nguyên payload từ log sang hệ thống có người đọc rộng hơn.

Kiểm tra **cấu hình logging framework đang chạy**, level hiệu lực theo namespace, appender/layout, HTTP access logging, reverse proxy, API gateway và collector. Không chỉ grep lời gọi logger trong controller rồi kết luận không có body leakage.

**Với exception**, giữ class của lỗi, mã nguyên nhân đã chuẩn hóa, route template và request ID; tránh ghép raw body hoặc raw rejected value vào thông điệp. Với lỗi nghiêm trọng cần stack trace, đánh giá khả năng exception message/cause chứa bí mật trước khi xuất ra các sink có quyền truy cập rộng.

## 13. Chiến lược diagnostic có kiểm soát nếu thật sự cần payload

Có những tình huống hiếm cần lưu một phần dữ liệu để tái hiện lỗi tích hợp. Thay vì bật “log all request bodies” cho cả hệ thống, nên thiết kế quy trình:

1. **Có mục đích, phạm vi và người chịu trách nhiệm rõ ràng.** Ví dụ chỉ endpoint tích hợp `/vendor/callback` trong staging, không phải tất cả request.
2. **Phân loại dữ liệu và áp policy trước khi thu thập.** Không dùng payload thực chứa credential, thẻ hoặc dữ liệu cá nhân nếu có thể tái hiện bằng dữ liệu tổng hợp.
3. **Allowlist sau parse**: chỉ các trường cần thiết cho chẩn đoán; không serialize toàn object graph.
4. **Áp limit và thời hạn.** Bounded size, sampling/chỉ request đã được chọn, feature flag có thời hạn và cơ chế rollback.
5. **Tách kênh lưu trữ** nếu cần bảo vệ nghiêm ngặt hơn application log thông thường; mã hóa, giới hạn truy cập, audit người xem, retention ngắn và quy trình xóa.
6. **Không copy raw body sang incident ticket/chat**. Chỉ dùng dữ liệu giả, request ID, mã lỗi hoặc reference được kiểm soát.
7. **Tắt diagnostic sau sự cố**, kiểm tra nơi dữ liệu còn tồn tại, bảo đảm không có log path bị quên.
8. **Kiểm chứng toàn pipeline** với canary trước khi áp dụng, kể cả console, appender phụ và collector.

Không dùng cơ chế này như “lối thoát” để bỏ qua chính sách không log secret. Với credential còn hiệu lực, không có quyền debug nào khiến việc ghi raw token thành bình thường nếu không có kiểm soát phù hợp.

## 14. Test: chứng minh log metadata mà không lộ body

### 14.1. Canary test với dữ liệu giả

Tạo request trong môi trường test chứa những marker **không phải secret thật**, ví dụ:

```json
{
  "email": "demo-user@example.test",
  "password": "CANARY_PASSWORD_NOT_REAL",
  "access_token": "CANARY_ACCESS_TOKEN_NOT_REAL",
  "notes": "line1\nline2"
}
```

Kích hoạt:
- Request thành công và thất bại validation.
- Exception parse JSON, missing required field, converter error.
- Endpoint đăng nhập/password reset.
- HTTP 401/403/500.
- Multipart upload và body lớn được giới hạn.
- Request chunked, client ngắt kết nối hoặc stream chưa đọc hết.
- Webhook, GraphQL variables và outbound HTTP retry khi có áp dụng.
- Chế độ INFO, DEBUG, TRACE **trong test/staging** (không bật production hàng loạt).

Kiểm tra dữ liệu canary **không xuất hiện** trong message, structured fields, MDC, exception text, file log, console, reverse proxy/gateway, log collector, backup hoặc alert. Tìm cả biến thể sau khi JSON escape/URL encode nếu integration có những phép biến đổi đó.

Một bài test chỉ kiểm tra `message` chưa đủ nếu encoder có thể xuất structured field `payload` độc lập.

### 14.2. Kiểm thử luồng body không bị phá

So sánh hành vi với logging filter **bật và tắt**:
1. Controller vẫn đọc đủ body và bind DTO đúng.
2. Validation trả đúng mã lỗi.
3. Request body rỗng, nhiều MB, chunked, multipart và streaming không bị filter làm thay đổi semantic.
4. Không có `IllegalStateException` do dùng `getReader()`/`getInputStream()` sai cách.
5. Không có memory leak hoặc tăng heap không kiểm soát dưới concurrent load.
6. WebFlux không bị double-subscribe hoặc mất backpressure.
7. Timeout/async dispatch vẫn ghi kết quả request nhất quán, không ghi hai event không chủ ý.

Với integration Spring MVC, chú ý trường hợp downstream **không đọc body**: một cache wrapper có thể trả về byte array rỗng, hoàn toàn không chứng minh request thực không có body.

### 14.3. Kiểm thử performance và resilience

Đo throughput, latency p50/p95/p99, CPU/GC, allocations, bytes log được xuất, số bản ghi bị drop và băng thông của collector. Một request body 1 MiB không nên biến thành một message log 1 MiB (hoặc nhiều lần 1 MiB qua nhiều appender) chỉ vì DEBUG được bật.

Nếu dùng appender bất đồng bộ, đo cả queue depth/flush. Nếu log sink lỗi hoặc chậm, nghiệp vụ phải theo chính sách rõ ràng; logging không nên là nguồn gây outage cho toàn bộ endpoint. Riêng audit bắt buộc có thể có chính sách đảm bảo bền vững khác và phải được thiết kế riêng.

## 15. Khi phát hiện body nhạy cảm đã lọt vào log

Xử lý theo quy trình security/privacy incident thay vì chỉ sửa một dòng:

1. **Chặn tiếp diễn:** ngừng log raw body, tắt wire/debug logging liên quan, sửa controller/filter/exception path và triển khai thay đổi.
2. **Xác định phạm vi:** loại body, thời gian, endpoint, service instances và những nơi đã lưu (console, file, collector, export, dashboard, backup, alert).
3. **Đánh giá credential:** nếu có password, token, API key hoặc cookie/session còn hiệu lực, cần revoke/rotate/reset theo policy phù hợp. Xóa log **không làm secret bị lộ trở lại an toàn**.
4. **Cô lập và xử lý dữ liệu đã lưu:** hạn chế quyền truy cập, thực hiện purge/quarantine/retention theo quy định áp dụng; tính đến các bản sao downstream và backup.
5. **Điều tra truy cập và nghĩa vụ thông báo:** phối hợp đội bảo mật, quyền riêng tư và vận hành; không suy đoán mọi loại thông tin đều có yêu cầu pháp lý giống nhau.
6. **Ngăn tái diễn:** bổ sung allowlist schema, test canary, code review các logger ghi `@RequestBody`/headers/DTO/exception, theo dõi thay đổi framework và config.

**Không đăng lại payload thật** lên ticket, chat hay phần mô tả lỗi. Dùng dữ liệu giả hoặc mã định danh sự cố được bảo vệ.

## 16. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Ghi `logger.debug("body={}", rawBody)` | Rò rỉ khi DEBUG bật; log có thể đến nhiều sink | Không log body; log metadata/field allowlist |
| Dùng `toJson(dto)` trước lời gọi logger | Vẫn serialize khi level tắt; có thể tạo bản sao bí mật | Không serialize DTO nhạy cảm cho log |
| Filter đọc `readAllBytes()` để xem payload | Consumes stream, heap tăng, phá controller | Không đọc body vì log; dùng metadata/field từ nghiệp vụ |
| `ContentCachingRequestWrapper` được coi là “body luôn có thể đọc lại” | Cache chỉ có bytes đã consume và có giới hạn | Hiểu lifecycle, test theo Spring/Servlet stack |
| Cắt 1 KiB đầu body và gọi là an toàn | Secret có thể ở ngay đầu | Dùng allowlist/redaction theo cấu trúc trước giới hạn |
| Regex che `password` rồi log cả JSON | Bỏ sót token, nested field, encoding khác | Không log raw, parse và chọn field an toàn |
| Log toàn bộ multipart/file upload | Chứa dữ liệu lớn, riêng tư hoặc nhị phân | Chỉ log metadata đã được phê duyệt |
| WebFlux subscribe thêm để log | Double consumption, lỗi backpressure/DataBuffer | Dùng observation/decorator đúng contract, không dump body |
| Lấy `Content-Length` làm số bytes nhận | Có thể -1/sai/chunked/đã biến đổi | Phân biệt declared vs measured bytes |
| Dùng raw URL như route | Query/path có thể mang token/PII | Dùng route template |
| In toàn exception parse lỗi | Message/cause có thể chứa fragment payload | Dùng error code, request ID và metadata đã kiểm soát |
| Chỉ redact ở dashboard | Raw body đã có thể ở stdout/file/collector | Loại body tại nguồn, test toàn pipeline |
| Không giới hạn bộ nhớ/cache hoặc logging queue | GC, OOM, backpressure, timeout | Giới hạn kích thước, queue, rate, retention |
| Bật TRACE toàn production để debug | Volume và diện rò rỉ rất lớn | Staging, sampling có kiểm soát, diagnostic hẹp |
| Log body vào MDC/ThreadContext | Mọi event cùng scope có thể nhận body | Không đưa body vào MDC; cleanup context |
| Tin request ID/header tùy ý | Log injection/giả mạo/truy vấn lẫn lộn | Sinh/validate/truncate mã tương quan |

## 17. Bài luyện tập và đáp án

**Bài 1 — Body stream.** Một Servlet filter gọi `request.getInputStream().readAllBytes()` rồi chuyển tiếp nguyên request cho controller để `@RequestBody` deserialize. Rủi ro chính là gì?

**Đáp án:** stream có thể đã bị tiêu thụ, controller không còn bytes như mong đợi; code còn tạo một bản sao kích thước không giới hạn và có thể lộ payload. Không đọc stream chỉ để log.

**Bài 2 — Ngưỡng 4 KiB.** Một hệ thống chỉ ghi 4 KiB đầu của JSON body. Có thể khẳng định không lộ mật khẩu/token không?

**Đáp án:** không. Secret thường ngắn và có thể nằm trong đoạn đầu. Giới hạn kích thước chỉ giảm tài nguyên/volume; biện pháp chính là **không ghi body** hoặc chọn field theo allowlist sau xử lý an toàn.

**Bài 3 — Spring wrapper.** `ContentCachingRequestWrapper.getContentAsByteArray()` trả rỗng khi một filter chạy sau chain. Có phải request chắc chắn không có body?

**Đáp án:** không. Có thể downstream không cần đọc body, request bị từ chối sớm hoặc cache chưa chứa bytes. Wrapper không tự đọc body lúc tạo.

**Bài 4 — Reactive.** Với WebFlux, có nên subscribe độc lập vào `Flux<DataBuffer>` để log rồi để controller subscribe lại?

**Đáp án:** không. Body là luồng theo contract của Reactor/Netty; double-subscribe hoặc giữ buffer sai có thể phá dữ liệu/backpressure. Ưu tiên metadata, nếu cần instrumentation thì dùng decorator tích hợp đúng lifecycle.

**Bài 5 — Structured logging.** Thay `logger.debug("body={}", body)` bằng `logger.atDebug().addKeyValue("body", body).log(...)` có làm body an toàn?

**Đáp án:** không. Structured JSON chỉ thay hình thức event; encoder vẫn có thể serialize giá trị của field `body`. Phải bỏ field đó hoặc thay bằng metadata/safe view.

**Bài 6 — Lộ secret.** Nếu một refresh token thật đã được ghi ra console và collector, sửa code để không ghi nữa có đủ không?

**Đáp án:** chưa đủ. Cần đánh giá scope, revoke token theo policy, kiểm soát các bản sao đã lưu và xử lý sự cố; không đăng lại token khi điều tra.

## 18. Checklist triển khai

Trước khi bật request logging trong ứng dụng web Java, hãy xác nhận:

1. **Không ghi raw request body** theo mặc định ở controller, filter, interceptor, AOP, exception handler, HTTP client, gateway hoặc collector.
2. Method, route, status, duration, request ID, body size và event code được lấy từ nguồn thích hợp; không làm lộ query/body bí mật.
3. Body stream **không bị đọc thêm hoặc tiêu thụ** chỉ để logging; controller/handler vẫn hoạt động đúng.
4. Nếu có Spring `ContentCachingRequestWrapper`, hiểu cache chỉ chứa bytes đã consumed và có giới hạn; không coi nó là API đọc lại body tùy ý.
5. Với WebFlux/streaming, giữ đúng consumption, backpressure, lifecycle `DataBuffer` và memory limits.
6. Multipart, file upload, binary/compressed bodies được xử lý bằng chính sách riêng; không convert bừa thành String.
7. Không serialize cả DTO/record/entity, không đưa raw body vào MDC, structured field hoặc exception message.
8. Nếu thu thập diagnostic đặc biệt, có **allowlist, mục đích, giới hạn, thời hạn và quyền truy cập** được duyệt; redaction tầng sau chỉ là defense in depth.
9. Các sink (console, file, appender phụ, collector, alert, backup) đã được kiểm tra bằng dữ liệu canary giả, kể cả DEBUG/TRACE và error path.
10. Có kiểm thử latency/CPU/heap/GC/log volume/queue và giám sát lỗi logging không ảnh hưởng quá mức đến nghiệp vụ.
11. Có quy trình xử lý sự cố khi payload nhạy cảm bị lọt log, bao gồm revoke/rotate credential và kiểm soát retention.

**Kết luận:** Request body có thể là dữ liệu lớn, không tin cậy và rất nhạy cảm. Logging raw body vừa có thể làm lộ bí mật, vừa tiêu thụ stream, tăng chi phí và gây lỗi vận hành. Trong ứng dụng web Java, cách làm bền vững là **không đưa body vào log event**, chỉ ghi metadata và trường đã được cho phép, giữ đúng lifecycle xử lý request, và xác minh toàn bộ pipeline bằng test và quan sát thực tế.