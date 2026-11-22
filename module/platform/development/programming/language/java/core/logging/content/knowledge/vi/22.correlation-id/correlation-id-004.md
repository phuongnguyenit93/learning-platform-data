# Truyền Correlation ID qua HTTP trong Java

## 1. Mục tiêu của bài học

Khi một request HTTP đi qua nhiều dịch vụ, mỗi dịch vụ thường có Logger, thread, process và log storage riêng. Ví dụ một thao tác thanh toán có thể đi theo tuyến:

~~~text
Browser / mobile client
       |
       v
API Gateway
       |
       v
Order Service --------> Inventory Service
       |
       v
Payment Service
~~~

Nếu Order Service ghi **"payment failed"** còn Payment Service ghi **"gateway timeout"**, làm sao biết hai sự kiện thuộc cùng một request? Một giải pháp là **Correlation ID**: một giá trị định danh được mang theo các HTTP request liên quan và xuất hiện trong log của từng dịch vụ. Khi điều tra, chỉ cần tìm những record có cùng ID để thu hẹp phạm vi.

**Truyền qua HTTP** nghĩa là xác định cách **nhận**, **kiểm tra**, **tạo khi thiếu**, **chuyển tiếp** và **trả về** một correlation ID thông qua HTTP headers; đồng thời gắn ID này vào logging context ở những nơi cần thiết.

Bài thuộc nhóm **Correlation ID** của **Java Core Logging**. Nội dung tập trung vào truyền ID qua HTTP, không biến thành hướng dẫn đầy đủ về authentication, distributed tracing hoặc idempotency.

Kết thúc bài, bạn có thể:

- Phân biệt **Correlation ID** với **request ID**, **trace ID**, **span ID** và **Idempotency-Key**.
- Chọn một hợp đồng HTTP header như **X-Correlation-ID** và hiểu tính **không phân biệt hoa/thường** của tên header.
- Xử lý header thiếu, rỗng, sai định dạng, quá dài hoặc có nhiều giá trị.
- Quyết định giữ incoming ID hay sinh ID mới tại một **trust boundary**.
- Chuyển ID sang request HTTP outbound, kể cả khi service gọi nhiều dependency.
- Đưa ID vào response và log; hiểu khi nào cần cấu hình CORS để client JavaScript đọc được response header.
- Viết ví dụ **Java 17** chạy độc lập với **HttpServer**, **HttpClient** và JUL Logger; xem stdout/stderr đã kiểm chứng.
- Xử lý scope và truyền logging context qua executor/async mà không rò ID giữa request.
- Thiết kế test để xác nhận propagation, validation và troubleshooting ở API gateway, service và downstream.
- Tránh dùng correlation ID như một credential, business key hoặc cơ chế bảo đảm mỗi request chỉ xử lý một lần.

## 2. Correlation ID là gì?

**Correlation ID** là mã định danh được dùng để **liên kết các sự kiện liên quan trong một luồng xử lý**. Nó không bắt buộc phải là UUID, nhưng cần format/độ dài đã thống nhất, đủ khó va chạm cho phạm vi sử dụng và không chứa dữ liệu nhạy cảm.

Ví dụ:

~~~text
Correlation ID: demo-42

gateway  | cid=demo-42 event=http.request.received
order    | cid=demo-42 event=order.accepted
payment  | cid=demo-42 event=payment.timeout
gateway  | cid=demo-42 event=http.request.failed status=502
~~~

Tìm theo **cid=demo-42** giúp thấy các record liên quan. Tuy nhiên, cùng ID chỉ cho biết chúng **được gắn cùng ngữ cảnh correlation**; không tự chứng minh quan hệ nhân quả, độ chính xác của dữ liệu hoặc tính duy nhất tuyệt đối.

### 2.1. Một ID có thể đi qua nhiều HTTP hops

Mẫu đơn giản:

~~~text
HTTP client
    |
    | X-Correlation-ID: demo-42
    v
Gateway
    |
    | X-Correlation-ID: demo-42
    v
Checkout Service
    |
    | X-Correlation-ID: demo-42
    v
Payment Service
~~~

Ở mỗi hop, ứng dụng đọc ID và:
1. Ghi vào log an toàn, theo một **field name thống nhất**.
2. Truyền chính ID đã được chấp nhận sang downstream.
3. Không tự tạo ID mới cho từng lời gọi nội bộ nếu muốn giữ mối liên kết end-to-end.

Đối với workflow nhiều bước, việc giữ nguyên một correlation ID không có nghĩa mọi operation đều là **cùng một HTTP request**. Gateway có request của nó, checkout có request khác, payment có request khác; nhưng chúng thuộc cùng ngữ cảnh tương quan.

### 2.2. Correlation ID không phải dữ liệu nghiệp vụ

Không dùng correlation ID để:
- Xác thực quyền truy cập hoặc xác định người dùng được phép làm gì.
- Làm session token, CSRF token, access token hoặc secret.
- Xác nhận một khoản tiền đã được thanh toán.
- Làm khóa duy nhất của order hoặc transaction business.
- Bảo đảm request retry không tạo thao tác trùng lặp.

ID phục vụ **observability và troubleshooting**, không thay hợp đồng nghiệp vụ.

## 3. Chọn HTTP header và định nghĩa contract

Một hệ thống có thể sử dụng custom header, ví dụ:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
X-Correlation-ID: demo-42
~~~

Đây là request HTTP minh họa; domain **example.test** chỉ dùng làm ví dụ, không phải địa chỉ của demo Java bên dưới.

**X-Correlation-ID là một tên thường gặp do hệ thống lựa chọn, không phải chuẩn chung bắt buộc của HTTP hoặc W3C Trace Context.** Tên khác như **X-Request-ID** cũng phổ biến. Trong một tổ chức, điều quan trọng là **chọn một tên chính thức**, xác định trách nhiệm mỗi component và bảo đảm tên được dùng nhất quán.

### 3.1. Tên HTTP header không phân biệt hoa/thường

Theo HTTP Semantics (RFC 9110), **tên field/header không phân biệt hoa thường**. Ví dụ:

~~~text
X-Correlation-ID
x-correlation-id
X-CORRELATION-ID
~~~

đều biểu diễn cùng một header name về mặt giao thức. Đừng viết code so sánh header name bằng một phép so khớp phân biệt hoa thường trên raw text request nếu framework đã có cấu trúc headers.

Trong Java 17:
- **HttpRequest.Builder.header("X-Correlation-ID", id)** đặt header trên outbound request.
- **HttpHeaders.firstValue("X-Correlation-ID")** lấy giá trị đầu nếu có.
- **HttpExchange.getRequestHeaders().get("X-Correlation-ID")** truy cập giá trị từ HttpServer Headers.

Các API headers làm việc với tên header theo semantics của HTTP; đoạn demo cố ý gửi chữ thường **x-correlation-id** rồi lấy bằng chữ hoa trong server để kiểm tra.

### 3.2. Xác định hợp đồng của giá trị

Không nên nhận một chuỗi không giới hạn từ client rồi đưa thẳng vào logs. Hợp đồng có thể quy định:

| Thuộc tính | Quy tắc ví dụ |
| --- | --- |
| Header name | X-Correlation-ID |
| Kiểu | ASCII String |
| Độ dài | 1–64 ký tự |
| Charset | A–Z, a–z, 0–9, dấu chấm, gạch dưới, gạch ngang |
| Ký tự đầu | Chữ hoặc số |
| Số giá trị | Chấp nhận đúng một giá trị |
| Thiếu/sai | Sinh ID mới hoặc trả lỗi, theo policy |
| Giá trị mới | UUID phiên bản 4 tạo ở phía server |
| Outbound | Truyền ID đã được chấp nhận |
| Response | Có thể trả lại ID để hỗ trợ điều tra |
| Logging | Field key chuẩn như correlation_id |

**Đây là policy minh họa, không phải RFC bắt buộc**. Một hệ thống khác có thể chỉ chấp nhận UUID canonical, dùng trace ID riêng hoặc phân biệt ID do gateway đáng tin cấp và ID từ Internet.

### 3.3. Vì sao phải giới hạn ký tự?

Client có thể cố gửi các giá trị có newline, ký tự điều khiển, Unicode lạ hoặc chuỗi dài. Nếu các giá trị này được chèn thẳng vào log text:
- Một giá trị có newline có thể tạo dòng log giả (**log injection**).
- Chuỗi cực dài làm tăng chi phí log/storage.
- Control characters gây lỗi parser hoặc trình hiển thị.
- Metadata từ client có thể bị hiểu nhầm là thông tin đáng tin.

Nên **validate trước khi log và forward**. Đừng ghi nguyên incoming ID không hợp lệ chỉ để “debug”; nếu cần telemetry về input xấu, ghi event code và reason có kiểm soát.

## 4. Quy trình inbound: nhận, kiểm tra, tạo khi thiếu

Ở ranh giới HTTP inbound, một thuật toán thực dụng:

~~~text
Nhận HTTP request
       |
       v
Đọc X-Correlation-ID
       |
       v
Đúng một giá trị hợp lệ?
  +----+----------------+
  | Có                  | Không
  v                     v
Giữ giá trị         Sinh ID mới
  |                     |
  +----------+----------+
             |
             v
Correlation ID được chấp nhận
             |
             +--> Gắn vào log context
             +--> Chuyển vào HTTP outbound
             +--> Có thể trả về response header
             |
             v
Cuối request: dọn logging context
~~~

### 4.1. Header thiếu

Nếu client chưa gửi correlation ID, server/gateway có thể tạo một ID mới để từ đó các log của request có chung khóa.

Ví dụ:

~~~java
String correlationId = UUID.randomUUID().toString();
~~~

Đây là đoạn Java minh họa, cần import java.util.UUID và nằm trong method phù hợp. UUIDv4 là một lựa chọn thông dụng cho ID mới; **không phải bí mật bảo mật**. Khi UUID không có ý nghĩa nghiệp vụ, không thể dùng nó để xác thực bất cứ điều gì.

### 4.2. Header rỗng, sai format hoặc quá dài

Ví dụ những giá trị cần loại theo policy ở mục 3:

~~~text
X-Correlation-ID:
X-Correlation-ID: bad value
X-Correlation-ID: includes/unsafe/path
X-Correlation-ID: [chuỗi rất dài vượt giới hạn]
~~~

Có ít nhất hai chiến lược hợp lệ tùy contract:
- **Generate-and-continue:** thay bằng ID mới, tiếp tục xử lý, có thể ghi warning loại input không hợp lệ.
- **Reject request:** trả **400 Bad Request** nếu API contract yêu cầu client phải gửi đúng ID.

Trong demo, ta chọn **generate-and-continue** để luồng HTTP không bị phụ thuộc vào việc client gửi header. Trong API bắt buộc correlation ID do gateway cấp, có thể chọn policy khác.

### 4.3. Có nhiều giá trị cùng tên header

Theo RFC 9110, các field lines cùng tên có thể được kết hợp tùy semantics của field. Với custom correlation ID được định nghĩa là **một token duy nhất**, danh sách nhiều giá trị hoặc giá trị đã gộp chứa dấu phẩy nên được xem là không hợp lệ trừ khi contract quy định rõ.

Ví dụ:

~~~http
X-Correlation-ID: a
X-Correlation-ID: b
~~~

Không nên tự chọn tùy tiện giá trị đầu tiên. Proxy, framework hoặc HTTP stack có thể gộp chúng theo cách khác. Demo dùng quy tắc **danh sách đúng một phần tử**, sau đó áp regex; nếu nhiều phần tử, sinh ID mới. Nếu proxy gộp thành **a, b**, giá trị chứa dấu phẩy cũng không qua regex.

**Quan trọng:** Unit test cho danh sách hai phần tử không hoàn toàn thay thế integration test qua proxy thực; cần kiểm thử cách proxy và server framework xử lý duplicate header fields.

### 4.4. Trust boundary quan trọng hơn tên header

Một ID do client tự gửi là **untrusted input**. Dù nó hợp regex, client vẫn có thể chọn **demo-42** cố tình trùng với ID của request khác. Điều này không cho client quyền truy cập log, nhưng có thể làm **nhiễu correlation** nếu hệ thống coi ID client cấp là nguồn tin cậy tuyệt đối.

Tùy risk model:
- Gateway có thể **luôn sinh correlation ID nội bộ mới** và chỉ lưu ID bên ngoài vào một field được kiểm soát riêng.
- Với clients đáng tin, gateway có thể giữ ID hợp lệ.
- Trước khi chuyển đến public external API, có thể **loại hoặc thay** internal correlation ID để không lộ metadata.
- Không dùng incoming ID làm rate-limit identity, security principal hoặc khóa chống trùng giao dịch.

Cần viết contract rõ ai được phép sinh, giữ, thay thế và nhận ID ở từng boundary.

## 5. Outbound: chuyển tiếp ID sang downstream HTTP request

Sau khi gateway chấp nhận ID **demo-42**, một lời gọi nội bộ có thể dùng:

~~~java
HttpRequest outbound = HttpRequest.newBuilder(downstreamUri)
        .header("X-Correlation-ID", correlationId)
        .GET()
        .build();
~~~

Đây là mảnh code minh họa trong method đã có **downstreamUri** và **correlationId**, cần import java.net.http.HttpRequest. Nó tạo một request mới và đặt header với ID đang có, **không tạo ID khác tại hop outbound**.

### 5.1. Giữ nguyên ID hay sinh ID con?

Đối với **một correlation ID xuyên dịch vụ**, thông thường giữ nguyên khi đi:
- Gateway → order service;
- order service → payment service;
- order service → inventory service;
- các lần retry thuộc cùng một request-level operation nếu cần phân tích chung.

Nếu muốn phân biệt từng attempt, hãy bổ sung **attempt_id**, **retry_count** hoặc **span_id**, không đổi correlation ID chính ở mỗi attempt.

Ví dụ:

~~~text
correlation_id=demo-42 attempt=1 event=payment.requested
correlation_id=demo-42 attempt=2 event=payment.requested
correlation_id=demo-42 attempt=2 event=payment.completed
~~~

Tùy contract, một background job hoặc event được tạo ra sau request cũng có thể mang **causation_id** hoặc **parent_correlation_id** thay vì giữ vĩnh viễn một ID cho mọi thao tác nhiều ngày. Mục tiêu là liên kết đúng phạm vi, không tạo một nhóm log không giới hạn.

### 5.2. Không tự động forward tất cả headers

Đừng lấy toàn bộ headers của inbound request rồi copy bừa sang mọi outbound request. Làm vậy có thể vô tình truyền cookie, Authorization, PII, secret hoặc header dành cho một hop/proxy khác.

Nên **allowlist** đúng những headers cần thiết và được phép truyền, trong đó có correlation ID đã được validate. Authorization/tracing context có policy riêng. **Correlation ID không phải credential**, nhưng vẫn cần cân nhắc mức độ công khai của ID.

### 5.3. Các HTTP client thường dùng

Trong Java 17, ví dụ dùng **java.net.http.HttpClient**. Các framework thực tế có thể dùng:
- Spring RestClient/RestTemplate/WebClient theo phiên bản framework;
- Apache HttpClient;
- OkHttp;
- JAX-RS Client;
- Feign hoặc một HTTP client được wrapper riêng.

Mẫu chung là đặt header tại **client interceptor/filter/request builder**. Dùng một cơ chế tập trung giúp giảm nguy cơ một endpoint quên forward ID, nhưng phải bảo đảm interceptor lấy **context đúng của request hiện tại**, không dùng một biến static chứa ID cuối cùng.

### 5.4. Outbound timeout và lỗi

Trong lúc gọi downstream, timeout hoặc IOException cũng phải được ghi với **correlation ID hiện hành**. Nếu client hết thời gian chờ trước khi downstream trả lời, downstream vẫn có thể đang xử lý; cùng ID giúp điều tra hai phía.

Không được mặc định **"timeout nghĩa là downstream chưa thực hiện gì"**. Với thao tác side-effect như thanh toán, retry cần idempotency semantics riêng; correlation ID chỉ để tìm logs.

## 6. Response header: giúp người gọi tìm log liên quan

Sau khi xử lý, API có thể trả:

~~~http
HTTP/1.1 200 OK
X-Correlation-ID: demo-42
Content-Type: text/plain; charset=UTF-8

downstream-ok
~~~

Nhờ đó, client hoặc support team có thể ghi lại correlation ID khi báo lỗi, thay vì phải tìm log bằng timestamp ước lượng.

Một response HTTP 500/502 cũng có thể trả ID tương ứng nếu server còn khả năng tạo response. Tuy nhiên:
- Nếu socket bị đóng hoặc reverse proxy tự tạo lỗi trước khi request vào app, app không đảm bảo response header có ID.
- Đừng tiết lộ secret/internal identifier có rủi ro trên public response; chỉ trả opaque ID theo policy.
- Không dùng sự có mặt của ID trong response làm bằng chứng request đã được xử lý thành công.

### 6.1. Đọc response header ở Java client

~~~java
String id = response.headers()
        .firstValue("X-Correlation-ID")
        .orElse("missing");
~~~

Đoạn minh họa cần biến **response** kiểu HttpResponse đã có. Java HttpHeaders.firstValue trả Optional; orElse giúp hiển thị khi response không có header. **Không mặc định mọi downstream đều echo header**, trừ khi hệ thống đã định nghĩa contract.

### 6.2. Browser CORS: client JavaScript đọc được header khi nào?

Đối với **cross-origin fetch**, một custom response header như **X-Correlation-ID** thường không được JavaScript đọc nếu server không expose nó theo CORS.

Khi policy cho phép, response có thể khai báo:

~~~http
Access-Control-Expose-Headers: X-Correlation-ID
~~~

Nếu browser JavaScript muốn **gửi custom X-Correlation-ID request header** cross-origin, CORS preflight còn có thể cần **Access-Control-Allow-Headers: X-Correlation-ID** cùng các thiết lập Allow-Origin/Methods/Credentials phù hợp.

**Không thêm wildcard CORS bừa bãi**; chỉ expose/allow đúng origins và headers được phép. Việc có CORS header không thay validation hoặc trust boundary của correlation ID. CORS áp dụng cho browser security model, không phải cơ chế bắt buộc của các Java HttpClient thông thường.

## 7. Gắn ID vào log mà không rò giữa request

Truyền header chỉ giải quyết **network propagation**. Để những log phát bên trong mỗi service hiển thị ID, cần có context tại code logging.

Một mẫu dùng SLF4J MDC:

~~~java
String previous = MDC.get("correlationId");
MDC.put("correlationId", acceptedId);
try {
    service.handleRequest();
} finally {
    if (previous == null) MDC.remove("correlationId");
    else MDC.put("correlationId", previous);
}
~~~

Đây là **mã minh họa trong application có SLF4J**, không phải chương trình độc lập; cần các biến/đối tượng được định nghĩa. Ý tưởng:
1. Đã có **acceptedId** sau khi kiểm tra incoming header.
2. Gắn vào MDC trước khi phần nghiệp vụ ghi log.
3. Trong Layout/Encoder, xuất MDC field **correlationId**.
4. Khôi phục giá trị cũ hoặc xóa key trong finally.

Trong Logback PatternLayout, ví dụ:

~~~text
%level|cid=%X{correlationId:-none}|%logger|%msg%n
~~~

Trong Log4j2 có cơ chế tương tự qua **ThreadContext** và PatternLayout. Trong JUL, có thể sử dụng Formatter/LogRecord hoặc logging context tự quản lý, tùy thiết kế. Demo chính dùng JUL và **đưa ID vào message đã validate**, để không phụ thuộc backend ngoài JDK; khi xây dựng service production, structured logging/MDC là lựa chọn dễ truy vấn hơn.

### 7.1. Không dùng biến static mutable chứa current correlation ID

Sai về thiết kế:

~~~java
static String currentCorrelationId;
~~~

Nếu hai request chạy đồng thời và cùng ghi biến, ID sẽ bị ghi đè và log bị trộn. Dùng:
- Request-scoped context;
- MDC/ThreadContext gắn với scope phù hợp;
- hoặc truyền một context object rõ ràng qua method arguments.

**ThreadLocal không phải propagation tự động qua mọi thread.** Khi chuyển sang ExecutorService/CompletableFuture/reactive execution, cần capture/restore context đúng boundary; thread pool có thể tái sử dụng thread cho request khác.

### 7.2. Dọn MDC trong finally là bắt buộc về tính đúng

Một request có thể throw exception, timeout, bị cancel hoặc trả về sớm. Nếu không cleanup, worker thread kế tiếp có thể ghi log với ID của request trước.

Mẫu có trách nhiệm:
- Gắn ID tại HTTP filter/interceptor.
- Dùng try/finally, bao gồm nhánh lỗi.
- Restore previous context nếu có scope lồng nhau.
- Capture + restore khi chuyển công việc sang worker thread.
- Không clear toàn bộ context của framework nếu chỉ sở hữu một key.

### 7.3. Structured logging là lựa chọn tốt cho phân tích

So sánh:

~~~text
INFO request completed cid=demo-42 status=200
~~~

với một event JSON:

~~~json
{
  "event": "http.request.completed",
  "level": "INFO",
  "service": "gateway",
  "correlation_id": "demo-42",
  "status_code": 200
}
~~~

Một backend có schema field **correlation_id** rõ ràng giúp filter exact match mà không phụ thuộc text parser. Nếu backend chỉ ghi raw message, bạn vẫn có thể search chuỗi; nhưng hãy ưu tiên field có kiểu và tên thống nhất khi cần dashboard hoặc tracing links.

**Đừng nhét ID nhạy cảm hoặc toàn bộ headers vào MDC tự động.** Context nên nhỏ, có allowlist, được dọn đúng vòng đời.

## 8. Ví dụ hoàn chỉnh Java 17: hai HTTP server và một client

Ví dụ sau dùng:
- **com.sun.net.httpserver.HttpServer** từ module **jdk.httpserver**;
- **java.net.http.HttpClient** thuộc Java 11+ và có trong Java 17;
- **java.util.logging.Logger/ConsoleHandler** để hiển thị log ra stderr;
- **UUID.randomUUID()** cho ID mới;
- **Pattern** để kiểm tra định dạng;
- hai HTTP servers chỉ bind **127.0.0.1**, mỗi server dùng **port 0** để hệ điều hành chọn cổng trống.

**Không cần Maven hay thư viện ngoài**. Tất cả nằm trong một file **CorrelationHttpDemo.java** có main() đầy đủ.

### 8.1. Sơ đồ thử nghiệm

~~~text
main() Java HttpClient
  |
  | GET /gateway
  | x-correlation-id: demo-42
  v
HttpServer gateway (127.0.0.1, random port)
  | validate -> accepts demo-42
  | LOG: cid=demo-42 event=gateway.received
  |
  | GET /downstream
  | X-Correlation-ID: demo-42
  v
HttpServer downstream (127.0.0.1, random port)
  | validate -> accepts demo-42
  | LOG: cid=demo-42 event=downstream.received
  | response: X-Correlation-ID: demo-42
  v
Gateway verifies downstream response header
  | LOG: cid=demo-42 event=gateway.completed
  | response: X-Correlation-ID: demo-42
  v
main() prints status/header/body
~~~

Vì HTTP header names không phân biệt hoa thường, phía client gửi **x-correlation-id** và phía server đọc theo tên **X-Correlation-ID** vẫn phù hợp.

### 8.2. Source file CorrelationHttpDemo.java

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.UUID;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.regex.Pattern;

public final class CorrelationHttpDemo {
    private static final String HEADER = "X-Correlation-ID";
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");
    private static final Logger GATEWAY = Logger.getLogger("gateway");
    private static final Logger DOWNSTREAM = Logger.getLogger("downstream");

    public static void main(String[] args) throws Exception {
        configure(GATEWAY);
        configure(DOWNSTREAM);

        HttpServer downstream = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        downstream.createContext("/downstream", exchange -> {
            String id = selectId(exchange.getRequestHeaders().get(HEADER));
            DOWNSTREAM.info("cid=" + id + " event=downstream.received");
            respond(exchange, 200, id, "downstream-ok");
        });

        HttpServer gateway = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3)).build();
        URI downstreamUrl = URI.create("http://127.0.0.1:"
                + downstream.getAddress().getPort() + "/downstream");
        gateway.createContext("/gateway", exchange -> {
            String id = selectId(exchange.getRequestHeaders().get(HEADER));
            GATEWAY.info("cid=" + id + " event=gateway.received");
            try {
                HttpRequest outgoing = HttpRequest.newBuilder(downstreamUrl)
                        .timeout(Duration.ofSeconds(3))
                        .header(HEADER, id)
                        .GET().build();
                HttpResponse<String> upstream = client.send(outgoing,
                        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
                if (!id.equals(upstream.headers().firstValue(HEADER).orElse(""))) {
                    throw new IOException("Downstream correlation mismatch");
                }
                GATEWAY.info("cid=" + id + " event=gateway.completed");
                respond(exchange, upstream.statusCode(), id, upstream.body());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                GATEWAY.warning("cid=" + id + " event=gateway.interrupted");
                respond(exchange, 502, id, "gateway-error");
            } catch (IOException ex) {
                GATEWAY.warning("cid=" + id + " event=gateway.upstream_failed");
                respond(exchange, 502, id, "gateway-error");
            }
        });

        try {
            downstream.start();
            gateway.start();
            URI gatewayUrl = URI.create("http://127.0.0.1:"
                    + gateway.getAddress().getPort() + "/gateway");
            HttpRequest request = HttpRequest.newBuilder(gatewayUrl)
                    .header("x-correlation-id", "demo-42")
                    .timeout(Duration.ofSeconds(3))
                    .GET().build();
            HttpResponse<String> response = client.send(request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

            System.out.println("response.status=" + response.statusCode());
            System.out.println("response.header="
                    + response.headers().firstValue(HEADER).orElse("missing"));
            System.out.println("response.body=" + response.body());
            System.out.println("missing.generatedUUID="
                    + isUuid(selectId(null)));
            System.out.println("invalid.generatedUUID="
                    + isUuid(selectId(List.of("bad value"))));
            System.out.println("duplicates.generatedUUID="
                    + isUuid(selectId(List.of("a", "b"))));
        } finally {
            gateway.stop(0);
            downstream.stop(0);
        }
    }

    private static String selectId(List<String> values) {
        return values != null && values.size() == 1
                && SAFE_ID.matcher(values.get(0)).matches()
                ? values.get(0) : UUID.randomUUID().toString();
    }

    private static boolean isUuid(String id) {
        try {
            UUID uuid = UUID.fromString(id);
            return uuid.version() == 4 && uuid.toString().equals(id);
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    private static void respond(HttpExchange exchange, int status,
                                String id, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(HEADER, id);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (var out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static void configure(Logger logger) {
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);
        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override public String format(LogRecord record) {
                return record.getLevel().getName() + "|"
                        + record.getLoggerName() + "|"
                        + record.getMessage() + System.lineSeparator();
            }
        });
        logger.addHandler(console);
    }
}
~~~

### 8.3. Biên dịch và chạy

Lưu source trong **CorrelationHttpDemo.java** tại một thư mục bất kỳ có quyền ghi. Chạy bằng JDK 17:

~~~bash
javac --release 17 -encoding UTF-8 CorrelationHttpDemo.java
java --add-modules jdk.httpserver CorrelationHttpDemo
~~~

Tùy môi trường module/classpath, **--add-modules jdk.httpserver** giúp nêu rõ module server trong lệnh chạy. Ví dụ đã được biên dịch với **javac --release 17** và chạy thành công trong một JVM Java có module này.

**Không đặt HttpClient của Java 17 trong try-with-resources.** Ở Java 17, HttpClient không implements AutoCloseable; ví dụ dùng HttpClient bình thường và quản lý hai HttpServer bằng **try/finally** để stop. Các API HttpClient đời JDK mới hơn có thể có khả năng quản lý vòng đời khác, nên khi học Java 17 phải tuân đúng API phiên bản này.

### 8.4. Stdout đã kiểm chứng

~~~text
response.status=200
response.header=demo-42
response.body=downstream-ok
missing.generatedUUID=true
invalid.generatedUUID=true
duplicates.generatedUUID=true
~~~

Ở demo, giá trị UUID được sinh ngẫu nhiên không in trực tiếp; chương trình chỉ kiểm tra chúng có dạng UUIDv4 canonical và in **true**. Nhờ đó kết quả stdout là **ổn định**, không phụ thuộc ID random.

### 8.5. Stderr đã kiểm chứng

**JUL ConsoleHandler ghi vào System.err**, không phải System.out. Với Formatter của demo, stderr là:

~~~text
INFO|gateway|cid=demo-42 event=gateway.received
INFO|downstream|cid=demo-42 event=downstream.received
INFO|gateway|cid=demo-42 event=gateway.completed
~~~

Nếu IDE gom stdout và stderr trong một console duy nhất, thứ tự hiển thị giữa hai stream có thể bị xen kẽ. Đây không phải bằng chứng propagation sai; hãy phân biệt streams và kiểm tra logging events theo ID, timestamp và mô hình thực thi.

### 8.6. Vì sao demo chấp nhận header viết thường?

HttpClient gửi:

~~~java
.header("x-correlation-id", "demo-42")
~~~

Trong khi gateway gọi:

~~~java
exchange.getRequestHeaders().get("X-Correlation-ID")
~~~

Hai tên được HTTP headers API xử lý như cùng một field name theo quy tắc case-insensitivity của HTTP. Việc normalize tên header không làm thay đổi **giá trị** ID; demo giữ **demo-42** xuyên các hop.

### 8.7. Vì sao phía downstream cũng validate?

Downstream nhận request từ gateway, nhưng một endpoint thật có thể được gọi từ nhiều nguồn hoặc chịu ảnh hưởng proxy. Do đó downstream vẫn có thể xác minh incoming value. Trong **mạng service-to-service đáng tin**, policy có thể chấp nhận ID của gateway nếu hợp lệ. Nếu muốn chống spoofing hoặc quy định khác tại boundary, cần thêm kiểm soát trust, không chỉ regex.

Trong demo, cả gateway và downstream áp cùng policy nên downstream giữ nguyên **demo-42**. Gateway còn kiểm tra header trong response upstream: nếu downstream trả ID khác, demo xem đây là mismatch và xử lý như lỗi gateway.

### 8.8. Ý nghĩa của ba dòng kiểm tra UUID

- **missing.generatedUUID=true**: nếu không có header, selectId(null) sinh UUIDv4.
- **invalid.generatedUUID=true**: chuỗi chứa khoảng trắng **"bad value"** không đạt regex, nên sinh UUIDv4.
- **duplicates.generatedUUID=true**: danh sách hai giá trị **["a","b"]** bị coi là ambiguous, nên sinh UUIDv4.

Đây là **unit-like checks của hàm selectId** đặt trong main; demo HTTP request thật chỉ kiểm tra trường hợp header hợp lệ. Khi cần bảo vệ production qua proxy, bổ sung integration tests gửi header thiếu/sai/lặp thực sự và kiểm tra cách framework canonicalize headers.

## 9. Phân tích các quyết định trong ví dụ

### 9.1. Tại sao bind 127.0.0.1?

Demo chỉ phục vụ test local. **127.0.0.1** không phải địa chỉ public, nên không mở một HTTP service thử nghiệm cho người khác trên mạng. Khi chạy server production, bind, TLS, authentication, concurrency và resource limits cần được quản lý bởi framework và hạ tầng phù hợp.

### 9.2. Tại sao dùng port 0?

Một port cố định như 8080 có thể đã được dùng bởi ứng dụng khác. **new InetSocketAddress("127.0.0.1", 0)** yêu cầu hệ điều hành cấp port trống khi HttpServer bind; sau đó code lấy **getAddress().getPort()** để xây URI. Điều này giúp demo dễ chạy lặp trên máy phát triển.

### 9.3. Tại sao chọn regex giới hạn 64 ký tự?

~~~java
Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
~~~

Mẫu này chỉ nhận 1–64 ký tự ASCII an toàn theo policy học tập:
- Ký tự đầu là chữ/số.
- 0–63 ký tự tiếp theo thuộc tập chữ/số/dấu chấm/gạch dưới/gạch ngang.
- Không nhận khoảng trắng, dấu phẩy, newline, slash hoặc chuỗi rỗng.

Nó **không chứng minh ID là duy nhất, đáng tin hay thuộc về một người dùng**. Regex chỉ là **format validation**. Khi boundary cần phân biệt trusted ID và client-provided ID, bổ sung chính sách riêng.

### 9.4. Tại sao hai server dùng cùng correlation ID?

Gateway nhận request ban đầu, kiểm tra ID rồi đặt vào outbound HttpRequest. Downstream đọc đúng ID đó, ghi log và echo trong response. Gateway kiểm tra echo, rồi trả lại ID cho caller. Cơ chế này cho phép lọc log xuyên services chỉ với một chuỗi **demo-42**.

Nếu gateway tạo ID khác cho outbound, hai phía có thể bị tách thành hai correlation groups. Nếu thực sự cần ID riêng cho sub-operation, dùng **parent ID**, **span ID** hoặc **attempt ID** trong schema thay vì âm thầm thay ID gốc.

### 9.5. Tại sao catch InterruptedException riêng?

HttpClient.send có thể ném **InterruptedException**. Khi bắt được, ví dụ gọi **Thread.currentThread().interrupt()** để khôi phục interrupt flag, ghi warning và cố gắng trả 502. Đây là thực hành đáng chú ý khi thao tác blocking có thể bị hủy. Trong server production, xử lý cancellation và response lifecycle cần phù hợp framework.

### 9.6. Giới hạn của phần mã dùng để học

Ví dụ không phải một reverse proxy production:
- Không có TLS, authentication, authorization hoặc rate limiting.
- Không có retry, circuit breaker, backpressure và thread pool riêng.
- Chỉ hỗ trợ một endpoint GET và body text cố định.
- Không có structured JSON logger hay MDC; ID được thêm vào message sau validation.
- Không validate HTTP status/body từ downstream ngoài kiểm tra correlation header.
- Chưa có chính sách CORS hay gắn ID ở một central middleware.
- Catch lỗi IO/interrupt chỉ nhằm minh họa; không bao phủ toàn bộ lỗi runtime, shutdown và trường hợp response đã bắt đầu gửi.
- Có thể thiếu log từ container/proxy trước khi request vào ứng dụng.
- Không dùng encryption hoặc secret quản lý ID vì correlation ID **không phải credential**.

Nếu triển khai thực tế, nên dùng framework HTTP và client interceptors/filter với lifecycle, observability, timeout và security policy đã được thiết kế.

## 10. Xây dựng middleware/filter cho ứng dụng thật

Không nên copy thao tác đọc và forward header vào từng controller theo kiểu rời rạc. Một cách có khả năng bảo trì tốt là đặt vào middleware.

### 10.1. Inbound filter

Trách nhiệm:
1. Đọc header đúng tên.
2. Validate số lượng/format/trust.
3. Chấp nhận hoặc sinh một ID mới.
4. Đặt vào request context và logging context.
5. Gọi application handler.
6. Trả ID vào response khi policy cho phép.
7. Dọn logging context trong finally.

Mã ý tưởng:

~~~java
String id = resolveCorrelationId(requestHeaders);
String previous = MDC.get("correlationId");
MDC.put("correlationId", id);
try {
    responseHeaders.set("X-Correlation-ID", id);
    nextHandler();
} finally {
    if (previous == null) MDC.remove("correlationId");
    else MDC.put("correlationId", previous);
}
~~~

Đây là **pseudocode tích hợp**: requestHeaders, responseHeaders, nextHandler và MDC adapter phải được thay bằng API framework thực tế. Đoạn này không chạy độc lập; khác với demo đầy đủ ở mục 8.

Nếu request được chuyển sang async callback sau khi filter return, middleware phải thiết kế propagation và response lifecycle theo framework, không giữ một ThreadLocal trên thread hiện tại đến lúc callback khác hoàn tất.

### 10.2. Outbound client interceptor

Trách nhiệm:
1. Lấy accepted ID từ request context (không tin biến toàn cục).
2. Validate hoặc chuẩn hóa nếu context được tạo từ dữ liệu khác.
3. Gắn header vào outbound request.
4. Không ghi đè ID khi một higher-level workflow đã định nghĩa parent/child context khác.
5. Không forward header ra ngoài trust domain nếu chính sách không cho phép.

Ví dụ logic:

~~~java
String id = requestContext.correlationId();
HttpRequest outgoing = HttpRequest.newBuilder(targetUri)
        .header("X-Correlation-ID", id)
        .GET().build();
~~~

Đây là đoạn minh họa: requestContext/targetUri được cung cấp bởi ứng dụng, không phải class độc lập. Một interceptor thực tế có thể được chạy trên nhiều thread hoặc xử lý concurrent requests; không lưu id trong state mutable của interceptor singleton.

### 10.3. Gateway và reverse proxy

Khi có reverse proxy trước ứng dụng, cần quyết định:
- Proxy có **giữ incoming ID** hay **tạo ID mới**?
- Proxy có gửi ID đến upstream như một header không?
- Header có bị strip hoặc đổi tên khi chuyển hop?
- Proxy tự tạo response 4xx/5xx có trả ID không?
- Nếu proxy và app cùng tạo ID, đâu là **nguồn authoritative**?
- Hệ thống có bao gồm CDN/load balancer ở nhiều trust zones không?

Thường nên có một điểm chấp nhận/sinh ID chính thức tại boundary đầu tiên được quản lý, sau đó downstream giữ nguyên theo contract. Nhưng lựa chọn cụ thể phải phù hợp bảo mật và khả năng tích hợp.

## 11. Correlation ID, traceparent và idempotency key khác nhau ra sao?

Ba khái niệm dễ bị trộn, nhất là trong ứng dụng microservices.

| Giá trị | Mục đích chính | Ghi chú |
| --- | --- | --- |
| **Correlation ID** | Nhóm log/event của một luồng xử lý | Có thể là custom HTTP header |
| **Request ID** | Xác định một HTTP request/boundary cụ thể | Có thể khác nhau qua từng hop |
| **W3C trace-id** | Định danh distributed trace | Thuộc chuẩn W3C Trace Context |
| **W3C parent-id/span ID** | Theo dõi operation/span trong trace graph | Không phải correlation ID tùy ý |
| **Idempotency-Key** | Cho backend nhận diện việc thử lại cùng một operation theo contract | Không thay authentication hoặc transaction management |
| **Business ID** | Xác định order, payment, invoice... | Có vòng đời nghiệp vụ khác |

### 11.1. W3C Trace Context

W3C chuẩn hóa các headers **traceparent** và **tracestate** cho distributed tracing. Ví dụ **traceparent**:

~~~http
traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01
~~~

Nó gồm version, trace-id, parent-id và trace-flags. Không nên thay toàn bộ header này bằng **X-Correlation-ID: demo-42** rồi cho rằng hệ tracing sẽ hiểu. Một system có thể **dùng đồng thời** X-Correlation-ID và traceparent, hoặc dùng trace-id làm correlation key trong logs khi kiến trúc đã tích hợp tracing.

Nếu có OpenTelemetry instrumentation, nên ưu tiên context propagation chuẩn của tracing framework. Đừng tự sửa traceparent tùy tiện: khi có span mới, parent/span semantics cần được thực hiện theo chuẩn, không chỉ copy nguyên chuỗi qua mọi operation.

### 11.2. Correlation ID và Idempotency-Key

**Idempotency-Key** trong một API có hỗ trợ idempotency thường giúp nhận diện một **attempt lặp lại của cùng operation** để hạn chế tạo side effect trùng, theo thời hạn và chính sách backend. Correlation ID chỉ giúp liên kết logs.

Ví dụ một client retry thanh toán:

~~~text
Attempt 1: correlation_id=demo-42; idempotency_key=pay-777
Attempt 2: correlation_id=demo-42; idempotency_key=pay-777
~~~

Dùng cùng correlation ID giúp tìm các logs của retry, nhưng **chỉ backend có cơ chế idempotency đúng mới quyết định có thực hiện thao tác lần nữa hay không**. Không dùng correlation ID trực tiếp làm khóa idempotency nếu contract không quy định; nó có thể có phạm vi và thời gian sống khác nhau.

### 11.3. Baggage không phải kho dữ liệu tùy tiện

Các hệ tracing có thể dùng W3C Baggage để truyền key–value context qua service boundaries. Nhưng baggage có thể được chuyển đến nhiều downstream services, nên chỉ lưu dữ liệu được phép chia sẻ và giới hạn kích thước; không đẩy token/PII vào baggage hoặc custom correlation header.

## 12. Những trường hợp HTTP thực tế cần quyết định rõ

### 12.1. Retry

Giữ **correlation ID** cho các attempts cùng logical operation khi muốn phân tích chung. Ghi thêm attempt number:

~~~text
cid=demo-42 attempt=1 event=downstream.timeout
cid=demo-42 attempt=2 event=downstream.success
~~~

Đừng tạo ID mới cho từng retry rồi không lưu mối liên hệ; việc đó làm điều tra khó khăn. Nếu cần ID theo từng attempt, đặt field riêng.

### 12.2. Fan-out song song

Một service có thể gọi payment và inventory cùng lúc:

~~~text
checkout
  | cid=demo-42
  +--> payment   (cid=demo-42)
  +--> inventory (cid=demo-42)
~~~

Cả hai outbound calls cần được truyền accepted ID. Với Java **CompletableFuture** hoặc ExecutorService, không đọc MDC của main request từ worker nếu chưa propagate context. Thay vào đó có thể truyền **id** như tham số rõ ràng tới task hoặc dùng context-aware wrapper.

### 12.3. Background task sau HTTP response

Nếu request kích hoạt một job chạy nhiều phút, cần quyết định job dùng:
- Cùng correlation ID để hỗ trợ tìm đầu-cuối;
- hay một jobId mới cộng parent_correlation_id để tránh một correlation group quá lớn.

Việc quyết định dựa trên semantic nghiệp vụ và observability. Nếu công việc chuyển qua message queue, HTTP header tự nhiên **không đi theo message**; cần map ID sang message headers/attributes theo hợp đồng messaging.

### 12.4. Redirect

Khi HTTP client tự follow redirects, cần kiểm tra chính sách chuyển tiếp headers và trust domain. Không mặc định custom correlation ID hoặc credential headers nên được forward tới mọi host trong redirect chain. Nếu có redirect sang một domain không đáng tin, cần hạn chế leaking internal context.

### 12.5. HTTP proxy hoặc service mesh

Proxy có thể thêm/trừ header, gộp duplicate fields hoặc tạo error response. Khi log upstream/downstream có ID khác, hãy kiểm tra:
- Header được đặt ở phía client trước khi request gửi chưa?
- Gateway có đổi tên hoặc strip không?
- Reverse proxy có tự tạo ID khác không?
- App có đọc đúng tên header không?
- Downstream có tự regenerate do validation thất bại không?
- Response header do app hay proxy ghi?
- ID có bị lấy từ một request context sai thread không?

### 12.6. HTTP/2 và case-insensitive header semantics

HTTP header names không phân biệt hoa thường về semantics; các phiên bản HTTP có quy định biểu diễn trên wire khác nhau. **Không dùng casing của header để mang thông tin nghiệp vụ**. Code nên xử lý cùng một field name nhất quán, qua framework/HTTP API chuẩn thay vì tự parse raw header lines.

## 13. Security, privacy và phòng chống log injection

Correlation ID thường được xem như metadata hỗ trợ debug, nhưng vẫn là dữ liệu có thể **bị client điều khiển**.

### 13.1. Không ghi raw untrusted header vào log

Sai:

~~~java
LOG.info("received cid=" + rawClientHeader);
~~~

Đây là đoạn minh họa với biến LOG và rawClientHeader. Nếu raw value chứa newline/control characters, output có thể tạo record giả; nếu quá dài có thể làm ngập log.

Nên:

~~~text
1. Read inbound header
2. Validate length, character set, duplicates and trust policy
3. Accept or generate safe ID
4. Log accepted ID
5. Propagate accepted ID to allowed destinations
~~~

Nếu muốn biết có client gửi ID xấu, ghi **event=correlation.invalid reason=bad_format**, không ghi nguyên dữ liệu có thể chứa nội dung độc hại.

### 13.2. Không nhúng thông tin nhạy cảm vào ID

Tránh tạo correlation ID như:

~~~text
user-email@example.test-order-42
phone-xxxx-xxxx
access_token_....
~~~

Một correlation ID nên là **opaque identifier**. Nếu ID chứa user ID hoặc tenant information, cần xem xét privacy policy, quyền truy cập và retention. Đặc biệt không dùng password, access token, refresh token, cookie, OTP hoặc private key.

### 13.3. Client-controlled ID không có quyền lực bảo mật

Ngay cả UUIDv4 từ client cũng không chứng minh client là chủ sở hữu ID đó. Vì vậy:
- Không dùng correlation ID để bypass authentication.
- Không cho phép API tìm log nội bộ chỉ bằng ID mà thiếu authorization.
- Không trả dữ liệu nhạy cảm chỉ vì người gọi biết ID.
- Không dùng ID client cung cấp như access-control principal.
- Không coi cùng ID là dấu hiệu tất cả các requests đều cùng user.

### 13.4. Header value size và resource budget

Hệ thống nên giới hạn overall HTTP headers và từng custom field theo hạ tầng. Nếu ID quá dài, policy nên reject hoặc generate mới. Không đặt hàng trăm metadata fields vào một header duy nhất hoặc tăng header buffer vô hạn chỉ vì muốn debug.

### 13.5. Log retention và exposure

Correlation ID có thể xuất trong:
- Application logs;
- proxy/access logs;
- tracing links;
- customer-facing response headers;
- ticket hỗ trợ.

Nó có thể giúp ghép dữ liệu qua các hệ thống. Vì thế retention và truy cập vẫn cần policy rõ; không công khai hệ thống tìm log nội bộ cho mọi người chỉ bằng correlation ID.

## 14. Testing: chứng minh propagation hoạt động

Các test hữu ích nên bao phủ **đầu vào**, **forwarding**, **response** và **logging**.

| Kịch bản | Kỳ vọng |
| --- | --- |
| Valid incoming ID | Gateway giữ ID, downstream và response dùng cùng ID |
| Tên header viết thường | Server vẫn đọc được |
| Header thiếu | Gateway sinh ID mới theo policy |
| Header rỗng hoặc khoảng trắng | Không đưa raw value vào logs |
| Header dài quá giới hạn | Reject hoặc tạo ID mới theo contract |
| Có hai giá trị header | Không tự chọn một giá trị ngẫu nhiên |
| Gateway → downstream | Outbound header chứa accepted ID |
| Downstream trả ID khác | Có detection và error policy rõ |
| Downstream timeout | Warning/error log vẫn có correlation ID |
| Concurrent requests | Không trộn ID giữa hai requests |
| Async task | Context có propagate/cleanup nếu cần |
| CORS browser | Custom response header chỉ expose khi policy cho phép |
| Proxy tạo error response | Quan sát ID của proxy và đường đối chiếu |
| Retry | Các attempts có correlation ID và attempt metadata phù hợp |
| External API boundary | Không forward internal IDs khi policy cấm |

### 14.1. Một kiểm tra request HTTP end-to-end

Trong demo Java 17, test đầu tiên gửi:

~~~text
x-correlation-id: demo-42
~~~

Sau đó xác nhận:
- Response status là 200;
- Response header là demo-42;
- Body là downstream-ok;
- Cả **gateway** và **downstream** đều có log cid=demo-42;
- Không có ID khác trong logging events của luồng này.

Đây là test thực sự qua HTTP localhost, không chỉ là gọi một hàm truyền String.

### 14.2. Test generation/validation

Bộ kiểm tra của demo gọi **selectId** trực tiếp với null, **"bad value"** và danh sách hai giá trị để xác nhận ID mới là UUIDv4. Đối với ứng dụng thực tế, nên bổ sung test HTTP gửi:
- Không có header;
- Header duplicate thực;
- Header quá dài;
- Ký tự không hợp lệ;
- Một proxy chuyển/gộp headers;
- Header bị thay bởi gateway.

**Tách unit test và integration test**: unit test kiểm tra thuật toán; integration test kiểm tra HTTP stack và những intermediaries thật.

### 14.3. Test concurrency

Chạy nhiều requests đồng thời, mỗi request có một ID khác. Xác minh không có log của request A mang ID của request B. Nếu sử dụng MDC, kiểm tra cleanup trên cùng worker thread sau khi request A kết thúc và task khác bắt đầu.

### 14.4. Test error path

Không chỉ test status 200. Cần test lỗi:
- Invalid input 400;
- Unauthorized 401/403;
- Downstream timeout 502/504 theo policy;
- Internal exception 500;
- Cancellation/interruption.

Bất cứ response nào do ứng dụng tạo ra nên tuân một chính sách rõ ràng về correlation ID; nếu proxy tạo response trước ứng dụng thì phần đó thuộc trách nhiệm proxy.

## 15. Những lỗi hay gặp khi truyền qua HTTP

### Lỗi 1 — Chỉ gắn ID vào inbound log

Gateway đọc header và log, nhưng outbound HttpClient không đặt lại header. Downstream không có correlation ID nên log không nối được.

**Sửa:** đặt header trên từng outbound request, tốt nhất qua client interceptor hoặc wrapper có test.

### Lỗi 2 — Tạo ID mới ở mọi service

Mỗi service tự tạo một UUID dù incoming ID hợp lệ. Mỗi hop có một correlation group khác nhau.

**Sửa:** xác định trust boundary; giữ accepted ID khi đi nội bộ và chỉ regenerate khi contract yêu cầu.

### Lỗi 3 — Tin mọi giá trị từ Internet

Server dùng raw header làm log value; client gửi newline, control characters hoặc chuỗi quá dài.

**Sửa:** validate format/length và áp dụng policy cho untrusted input trước khi log/forward.

### Lỗi 4 — Chọn giá trị đầu trong header lặp

Client gửi hai X-Correlation-ID, server tự chọn firstValue mà không có contract, tạo ambiguous correlation.

**Sửa:** quy định đúng một giá trị; duplicate/gộp thành comma không hợp lệ nếu policy chỉ chấp nhận một token.

### Lỗi 5 — Sai tên header giữa các services

Gateway đặt **X-Correlation-ID**, Payment Service đọc **X-Request-ID**, dẫn đến tự tạo ID mới.

**Sửa:** chuẩn hóa contract, cân nhắc mapping tại boundary, test hop-to-hop.

### Lỗi 6 — Không echo ID cho client

Client gặp lỗi nhưng không biết mã để báo support.

**Sửa:** có response header phù hợp, khi security/privacy policy cho phép; trong browser cross-origin cần CORS expose header.

### Lỗi 7 — Log ID trong message nhưng mất khi async

Request thread có context, task chạy trong ExecutorService không có context hoặc giữ ID cũ.

**Sửa:** truyền ID rõ ràng hoặc capture/restore MDC theo framework; cleanup bắt buộc.

### Lỗi 8 — Dùng correlation ID làm Idempotency-Key

Retry có cùng ID nên backend mặc định coi là một transaction.

**Sửa:** thiết kế idempotency riêng, có storage/expiration/semantics; correlation ID không mang tính transaction guarantee.

### Lỗi 9 — Nhầm với traceparent

Một service tự gắn X-Correlation-ID rồi kỳ vọng hệ distributed tracing có spans/parent relationships.

**Sửa:** instrument tracing đúng chuẩn W3C/OpenTelemetry khi cần trace; giữ correlation ID như metadata bổ trợ nếu hữu ích.

### Lỗi 10 — Lộ internal ID ra external service

HTTP client tự forward tất cả inbound headers, vô tình gửi correlation metadata và credential đến host không đáng tin.

**Sửa:** allowlist headers theo trust boundary, kiểm soát redirects và outbound destinations.

### Lỗi 11 — Cho rằng header luôn có trong mọi error response

Gateway hoặc proxy có thể trả 502 trước khi app xử lý; app không thể gắn ID cho response đó.

**Sửa:** định nghĩa tracing/logging ở tầng ingress/proxy và chính sách response tại từng boundary.

### Lỗi 12 — Không kiểm tra backend logging

MDC đã có ID nhưng PatternLayout không xuất field, hoặc service log bị collector drop.

**Sửa:** test output thực tế từ producer đến storage; kiểm tra level/filter/schema, sampling và ingestion health.

## 16. Bài tập mở rộng

### Bài A — Thiếu header qua HTTP

Sửa HttpRequest trong main để không đặt X-Correlation-ID. Thay vì chỉ kiểm tra selectId(null), gửi request thật qua gateway và kiểm tra response trả UUIDv4, log gateway/downstream có **cùng UUID**. Chú ý giá trị random sẽ khác giữa các lần chạy; đừng hardcode stdout có UUID cụ thể.

### Bài B — Header sai format

Gửi một value chứa khoảng trắng nếu HTTP client cho phép truyền giá trị đó. Xác minh gateway áp policy generate mới và downstream dùng ID được chấp nhận. Đối với control characters, nhiều HTTP clients sẽ từ chối ngay tại builder; test rejection ở unit layer phù hợp.

### Bài C — Duplicate headers

Thử HTTP client/proxy gửi nhiều field lines cùng tên, xác minh server/framework cung cấp các giá trị thế nào. Không giả định luôn trả List có đúng hai phần tử khi proxy có thể gộp values bằng dấu phẩy.

### Bài D — Thêm request ID riêng theo hop

Giữ correlationId=demo-42 xuyên gateway và downstream, nhưng tại mỗi hop sinh **request_id** riêng. Log cả correlation_id và request_id, rồi thử group theo từng field.

### Bài E — Truyền sang hai downstream

Thêm Inventory Server. Gateway gọi Payment và Inventory song song. Đảm bảo cả hai nhận đúng accepted ID. Nếu dùng CompletableFuture, truyền ID theo task parameters hoặc context propagation có cleanup.

### Bài F — Timeout

Cho downstream phản hồi chậm hơn request timeout. Quan sát warning của gateway; đảm bảo log vẫn mang correlation ID dù không nhận được response. Suy nghĩ tại sao không nên tự động retry một POST có side effect nếu không có idempotency contract.

### Bài G — Response CORS

Mô phỏng browser cross-origin gọi API. Khi được phép, thêm Access-Control-Expose-Headers và Access-Control-Allow-Headers phù hợp. Kiểm tra JavaScript đọc được response header nhưng không tạo chính sách CORS mở vô điều kiện.

### Bài H — W3C traceparent

Dùng tracing library tạo spans và truyền traceparent. Giữ custom X-Correlation-ID như field phụ. So sánh trace-id, span-id và correlation-id trong logs, không tự sửa traceparent bằng nối chuỗi tùy ý.

### Bài I — Logging security

Tạo các giá trị ID chứa newline, dấu phẩy, ký tự không hợp lệ và chuỗi quá dài. Viết unit tests cho selectId. Xác nhận raw input không bao giờ xuất vào log và không được forward.

### Bài J — Production design

Viết checklist cho một ứng dụng HTTP lớn: ingress proxy, inbound filter, outbound client interceptor, MDC lifecycle, retries, async tasks, CORS, log collector, retention và security boundary. Phân biệt thành phần nào sinh ID và thành phần nào chỉ giữ/forward.

## 17. Câu hỏi kiểm tra và đáp án

**1. Truyền Correlation ID qua HTTP thường dùng vị trí nào?**  
Một HTTP request header được thống nhất giữa các dịch vụ, ví dụ X-Correlation-ID; response có thể echo ID khi policy cho phép.

**2. X-Correlation-ID có bắt buộc là header chuẩn của HTTP không?**  
Không. Đây là một convention/custom header, cần có contract nhất quán.

**3. HTTP header name có phân biệt hoa/thường không?**  
Không. Tên header được so khớp case-insensitively theo HTTP Semantics.

**4. Nếu header thiếu thì nên làm gì?**  
Tùy contract: thường sinh ID an toàn mới ở boundary, hoặc reject nếu API bắt buộc ID do upstream cấp.

**5. Vì sao phải kiểm tra header value trước khi log?**  
Để giới hạn kích thước, ngăn ký tự điều khiển/log injection, tránh giá trị ambiguity và bảo vệ trust boundary.

**6. Khi gateway đã nhận ID hợp lệ, downstream nên nhận ID nào?**  
Cùng accepted correlation ID nếu muốn liên kết end-to-end; ID riêng cho attempt/span được ghi ở field khác.

**7. Nếu một request có 3 retries, có cần 3 correlation IDs không?**  
Thường dùng một correlation ID chung và attempt metadata, trừ khi contract quy định khác.

**8. Correlation ID có ngăn thanh toán bị xử lý lặp không?**  
Không. Cần cơ chế idempotency được định nghĩa, không dựa vào correlation ID.

**9. Chỉ có X-Correlation-ID có tạo distributed trace không?**  
Không. W3C Trace Context có traceparent/tracestate và hệ instrumentation/span propagation.

**10. Java HttpClient có tự forward inbound headers khi tạo outbound request không?**  
Không. Code hoặc interceptor phải chủ động chọn và đặt headers được phép.

**11. Tại sao nên trả ID trong response?**  
Giúp client/support liên kết request gặp lỗi với logs; chỉ khi privacy/security policy cho phép.

**12. Browser JavaScript có thể đọc mọi custom response header cross-origin không?**  
Không mặc định. Cần CORS Access-Control-Expose-Headers cho custom header được phép.

**13. Vì sao MDC cần cleanup trong finally?**  
Để tránh thread được tái sử dụng cho request khác vẫn mang ID cũ.

**14. Tại sao không dùng static String currentCorrelationId?**  
Vì concurrent requests có thể ghi đè, tạo log sai correlation.

**15. Trong demo, ba log stderr thuộc đâu?**  
Một gateway.received, một downstream.received và một gateway.completed; cùng cid=demo-42.

**16. Vì sao stdout in ba giá trị generatedUUID=true mà không in UUID cụ thể?**  
Vì UUID được sinh ngẫu nhiên. Kiểm tra điều kiện giúp stdout ổn định và không phải đoán một ID bất kỳ.

**17. Trong Java 17, HttpClient có dùng try-with-resources được không?**  
Không. HttpClient của Java 17 không implements AutoCloseable; quản lý vòng đời các HTTP servers bằng finally như demo.

**18. Một correlation ID giống nhau có chứng minh hai sự kiện cùng một người dùng không?**  
Không. ID có thể do client cung cấp, va chạm hoặc được sử dụng trên nhiều steps; authentication/security context là cơ chế khác.

## 18. Tài liệu chính thức

- IETF RFC 9110 — HTTP Semantics, field names và duplicated field values: https://www.rfc-editor.org/rfc/rfc9110.html
- W3C Trace Context — traceparent/tracestate: https://www.w3.org/TR/trace-context/
- Java SE 17 — HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Java SE 17 — HttpRequest: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html
- Java SE 17 — HttpHeaders: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpHeaders.html
- Java SE 17 — HttpServer: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Java SE 17 — UUID: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/UUID.html
- SLF4J MDC API: https://www.slf4j.org/api/org/slf4j/MDC.html
- OpenTelemetry Context Propagation: https://opentelemetry.io/docs/concepts/context-propagation/

Khi vận dụng, kiểm tra đúng version Java/framework, chính sách API gateway, tên custom headers và contract tracing đang được triển khai. Ví dụ **X-Correlation-ID** cùng regex/UUIDv4 trong bài là **một chính sách minh họa** chứ không phải tiêu chuẩn HTTP duy nhất.

## 19. Ghi nhớ cốt lõi

**Truyền Correlation ID qua HTTP** là một hợp đồng xuyên service gồm **đọc incoming header → validate/trust decision → chấp nhận hoặc tạo ID → gắn vào log → truyền sang outbound request → có thể echo trong response → cleanup context**.

Để có kết quả tốt, hãy giữ tên header và schema thống nhất, không forward dữ liệu client chưa kiểm tra, không dùng ID cho authorization/idempotency, không quên async context propagation và đừng nhầm custom correlation ID với W3C traceparent. Ví dụ Java 17 đã chạy thực tế cho thấy gateway và downstream giữ nguyên **demo-42**, response trả đúng ID, các tình huống thiếu/sai/lặp được kiểm tra riêng và log của hai HTTP services có thể được tìm bằng cùng một khóa correlation.
