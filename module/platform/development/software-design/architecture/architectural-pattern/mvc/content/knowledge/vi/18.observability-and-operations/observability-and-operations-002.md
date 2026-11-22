# Định danh tương quan từ giao diện tới dịch vụ phụ thuộc

Khi người dùng nhấn nút lưu trên giao diện, request có thể đi qua trình duyệt, reverse proxy, ứng dụng MVC, application service, cơ sở dữ liệu và một hoặc nhiều dịch vụ bên ngoài. Nếu thao tác thất bại hoặc chậm, đội vận hành cần lần theo đúng request qua các thành phần đó. Chỉ nhìn một dòng log như “Không thể lưu đơn hàng” thường không đủ để biết request đã đi đến đâu, mất bao lâu ở từng bước và lỗi bắt đầu từ thành phần nào.

**Định danh tương quan** giúp liên kết các log, span và sự kiện thuộc cùng một luồng xử lý. Trong hệ thống phân tán, trace context cho phép truyền ngữ cảnh theo chuẩn giữa các dịch vụ. Với ứng dụng **Model–View–Controller (MVC)**, việc này cần bắt đầu từ tương tác trên giao diện, đi qua Controller và các tầng ứng dụng, rồi tiếp tục tới dịch vụ phụ thuộc hoặc tác vụ bất đồng bộ.

Bài học này phân biệt correlation ID, trace ID và span ID; mô tả cách truyền ngữ cảnh qua HTTP, CORS và message broker; hướng dẫn tích hợp với OpenTelemetry và logging; đồng thời chỉ ra các rủi ro khi dùng định danh tương quan sai cách. Mục tiêu là để một thao tác của người dùng có thể được điều tra xuyên suốt mà không biến ID kỹ thuật thành thông tin xác thực hoặc dữ liệu nhạy cảm.

## 1. Vì sao cần định danh tương quan?

Giả sử người dùng tạo đơn hàng. Giao diện gửi request đến ứng dụng MVC. Controller gọi dịch vụ đơn hàng, dịch vụ này đọc kho dữ liệu, gọi dịch vụ tính phí vận chuyển và gửi yêu cầu thanh toán. Nếu thanh toán timeout, đội hỗ trợ cần trả lời:

- Request nào của người dùng gặp lỗi?
- Ứng dụng đã nhận request và xử lý ở Controller nào?
- Dịch vụ nào được gọi trước khi timeout?
- Request tới dịch vụ phụ thuộc có thực sự được gửi không?
- Tổng thời gian nằm ở ứng dụng, mạng hay dịch vụ bên ngoài?
- Có lần retry nào đã xảy ra?

Nếu mỗi thành phần ghi log bằng một định dạng ID khác nhau hoặc không ghi ID, việc điều tra phải dựa vào timestamp, URL và phỏng đoán. Nhiều người dùng có thể gửi cùng endpoint trong cùng một giây, nên timestamp đơn lẻ không đủ để liên kết sự kiện.

Một định danh tương quan được truyền nhất quán giúp:

- Tìm tất cả log liên quan đến một request hoặc hành trình.
- Ghép span của nhiều dịch vụ thành một distributed trace.
- Đối chiếu lỗi hiển thị cho người dùng với log nội bộ.
- Đo thời gian từng đoạn và xác định nơi phát sinh độ trễ.
- Theo dõi retry, message và công việc nền liên quan.

## 2. Phân biệt correlation ID, trace ID và span ID

Ba khái niệm này liên quan nhưng không đồng nghĩa.

| Định danh | Phạm vi | Mục đích | Ví dụ |
|---|---|---|---|
| Correlation ID | Một request, một phiên nghiệp vụ hoặc một hành trình theo quy ước của hệ thống | Tìm log và sự kiện liên quan | req-7f3a... |
| Trace ID | Toàn bộ distributed trace | Liên kết các span qua nhiều thành phần | Chuỗi hex 32 ký tự |
| Span ID | Một thao tác cụ thể trong trace | Xác định một đoạn xử lý và quan hệ cha/con | Chuỗi hex 16 ký tự |

**Correlation ID** thường là quy ước của ứng dụng. Một request có thể nhận một ID riêng, hoặc nhiều request của cùng một quy trình nghiệp vụ có thể chia sẻ một business correlation ID. Vì phạm vi tùy hệ thống, cần ghi rõ ý nghĩa của nó.

**Trace ID** thuộc mô hình tracing phân tán. Tất cả span trong cùng một trace dùng chung trace ID. Một trace có thể gồm nhiều span qua gateway, MVC server, dịch vụ thanh toán và dịch vụ vận chuyển.

**Span ID** nhận diện một thao tác cụ thể, chẳng hạn xử lý HTTP request ở ứng dụng MVC hoặc gọi API thanh toán. Span con có parent span ID để biểu diễn quan hệ gọi.

Một trace có thể hình dung như sau:

~~~mermaid
flowchart TD
    T[Trace ID: T1]
    T --> A[Span S1: Browser request]
    A --> B[Span S2: MVC server]
    B --> C[Span S3: Order service]
    C --> D[Span S4: Database query]
    C --> E[Span S5: Shipping API]
    C --> F[Span S6: Payment API]
~~~

Trong thực tế, browser span có thể được ghi ở hệ thống Real User Monitoring (RUM), còn server span được ghi ở backend. Không phải mọi hệ thống đều tạo browser span; điều quan trọng là ngữ cảnh được truyền đúng và các công cụ có thể liên kết dữ liệu khi có đủ telemetry.

## 3. Một thao tác có thể có nhiều loại ID

Không nên ép một ID làm mọi nhiệm vụ. Một hệ thống có thể dùng:

- **Request ID:** định danh một lần HTTP request tại một ranh giới cụ thể.
- **Trace ID:** liên kết các span của một lần xử lý phân tán.
- **Correlation ID:** liên kết các sự kiện thuộc một hành trình hoặc quy trình nghiệp vụ dài hơn.
- **Business ID:** định danh thực thể như order ID, payment ID hoặc job ID.

Ví dụ, người dùng bấm “Tạo đơn” một lần nhưng trình duyệt thử gửi lại do mạng chập chờn. Mỗi lần HTTP request có thể có request ID và trace ID riêng, trong khi cùng tham chiếu một idempotency key hoặc business operation ID để nhận biết chúng thuộc cùng ý định nghiệp vụ.

Một đơn hàng có thể được xử lý trong nhiều phút hoặc nhiều giờ qua các message và tác vụ nền. Khi đó, business ID hoặc correlation ID nghiệp vụ giúp liên kết các trace riêng theo thời gian. Không nên giữ một trace mở xuyên suốt một quy trình kéo dài nhiều ngày; hãy tạo trace mới cho từng lần xử lý và liên kết chúng bằng business correlation ID hoặc span link phù hợp.

## 4. W3C Trace Context và header traceparent

Để truyền ngữ cảnh tracing qua HTTP, chuẩn W3C Trace Context định nghĩa các header chính:

- **traceparent:** mang trace ID, parent span ID và trace flags.
- **tracestate:** mang thông tin vendor-specific để các hệ thống tracing phối hợp.

Một header traceparent minh họa:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Cấu trúc gồm:

~~~text
version-trace-id-parent-id-trace-flags
~~~

Trong ví dụ:

- 00 là version.
- 4bf92f3577b34da6a3ce929d0e0e4736 là trace ID.
- 00f067aa0ba902b7 là parent span ID.
- 01 là trace flags; bit sampled được bật trong ví dụ.

Khi dịch vụ A gọi dịch vụ B, instrumentation tạo span client cho lời gọi đó và truyền trace context. Dịch vụ B tiếp nhận context, tạo span server con và tiếp tục truyền ngữ cảnh nếu gọi dịch vụ khác.

Không nên tự nối chuỗi traceparent bằng tay hoặc tự tạo ID không đúng định dạng. Dùng OpenTelemetry SDK/agent hoặc thư viện tracing hỗ trợ chuẩn để tạo, trích xuất và inject context.

## 5. Luồng tương quan từ trình duyệt tới dịch vụ phụ thuộc

Một luồng web điển hình:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant UI as Browser / UI
    participant G as Gateway
    participant MVC as MVC Application
    participant S as Order Service
    participant P as Payment Service
    participant O as Observability Backend

    User->>UI: Nhấn Tạo đơn
    UI->>G: HTTP request + trace context
    G->>MVC: Forward request + trace context
    MVC->>S: Gọi use case + trace context
    S->>P: Gọi thanh toán + trace context
    P-->>S: Kết quả / lỗi
    S-->>MVC: Kết quả use case
    MVC-->>UI: HTTP response + request reference
    UI-->>User: Hiển thị kết quả
    MVC->>O: Export spans và logs
    S->>O: Export spans và logs
    P->>O: Export spans và logs
~~~

Gateway có thể tạo trace mới nếu request chưa có context hợp lệ, hoặc tiếp tục context từ upstream theo chính sách của hệ thống. MVC application tạo span server, các service tạo span cho thao tác nội bộ và outbound call. Tất cả dữ liệu telemetry được gửi đến hệ thống thu thập quan sát.

Giao diện không nhất thiết phải biết toàn bộ chi tiết span. Nó chỉ cần truyền context qua công cụ instrumentation phù hợp và có thể hiển thị một mã hỗ trợ an toàn khi thao tác thất bại.

## 6. Tạo hoặc tiếp nhận định danh ở ranh giới HTTP

Khi request đi vào hệ thống, cần quyết định thành phần nào là nơi tạo hoặc tiếp nhận định danh:

- API gateway có thể tạo request ID và trace context ban đầu.
- Ứng dụng MVC có thể tạo request ID nội bộ nếu gateway không cung cấp.
- OpenTelemetry instrumentation quản lý trace context theo chuẩn.
- Business correlation ID có thể được tạo khi bắt đầu một use case hoặc quy trình nghiệp vụ.

Không nên tin vô điều kiện mọi header định danh do client gửi. Client có thể gửi chuỗi rất dài, ký tự điều khiển hoặc một ID trùng với request khác để làm nhiễu log. Nếu cần nhận X-Correlation-ID từ upstream, chỉ tin nguồn đã xác định, giới hạn độ dài và tập ký tự, đồng thời có chính sách thay thế khi không hợp lệ.

Trace context không phải credential. Người gửi có thể cung cấp trace ID hoặc parent context; hệ thống vẫn phải xác thực và phân quyền độc lập. Không dùng trace ID để cho phép truy cập log, dữ liệu hoặc thao tác quản trị.

## 7. Tạo request ID và đưa vào log trong Spring MVC

Với correlation ID riêng của ứng dụng, có thể tạo ID tại một Servlet filter và đưa vào logging context. Ví dụ sau luôn tạo ID nội bộ mới cho mỗi request, trả ID trong response header và đặt nó vào MDC:

~~~java
@Component
public class RequestCorrelationFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String requestId = UUID.randomUUID().toString();
        response.setHeader("X-Request-ID", requestId);

        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("requestId", requestId)) {
            filterChain.doFilter(request, response);
        }
    }
}
~~~

Đây là request ID để hỗ trợ tra log, không phải distributed trace ID. Trong ứng dụng dùng Spring Boot với Micrometer Tracing hoặc OpenTelemetry, trace ID và span ID nên được tích hợp vào logging context bởi instrumentation tương ứng. Không tự tạo trace ID riêng bằng UUID rồi giả định nó sẽ nối được với trace của dịch vụ phụ thuộc.

Nếu muốn giữ một correlation ID từ gateway, hãy xác định gateway là nguồn tin cậy và validate header trước khi dùng. Có thể lưu cả upstream request ID và internal request ID trong log nếu cần phân biệt nguồn.

### 7.1. Dọn logging context đúng lúc

MDC thường gắn dữ liệu với thread hiện tại. Filter phải xóa context sau khi request kết thúc để thread được tái sử dụng không mang ID của request trước. Ví dụ dùng MDC.putCloseable ở trên tự đóng trong khối try.

Với async Servlet request, executor hoặc reactive pipeline, thread có thể thay đổi. MDC không tự động bảo đảm context truyền đúng qua mọi thread. Dùng cơ chế context propagation của framework hoặc tracing library; không dựa vào ThreadLocal thuần cho xử lý bất đồng bộ.

## 8. Lấy trace ID và span ID trong code

Khi dùng OpenTelemetry API, có thể đọc context span hiện tại để thêm thông tin vào thông báo hỗ trợ hoặc log:

~~~java
SpanContext context = Span.current().getSpanContext();

if (context.isValid()) {
    String traceId = context.getTraceId();
    String spanId = context.getSpanId();
    log.info("Processing order traceId={} spanId={}", traceId, spanId);
}
~~~

Đoạn code chỉ đọc span hiện tại. Nó không tạo span mới và không thay thế instrumentation. Nếu không có span hợp lệ, ứng dụng không nên giả định luôn có trace ID; có thể ghi request ID riêng hoặc để trống theo schema log.

Không nên đưa span ID vào mọi thông điệp người dùng. Trace ID có thể hữu ích làm mã hỗ trợ, nhưng nên cân nhắc liệu hệ thống có cho phép người dùng tra cứu bằng ID đó hay chỉ hiển thị một request reference riêng.

## 9. Truyền context từ browser tới backend

Với giao diện sử dụng JavaScript gọi API, có thể dùng OpenTelemetry JavaScript hoặc RUM SDK hỗ trợ distributed tracing. Instrumentation sẽ tạo hoặc tiếp nhận trace context, sau đó inject header khi gửi request đến backend trong phạm vi được cấu hình.

Một request có thể trông như:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Không nên tự viết mã JavaScript tạo trace ID ngẫu nhiên rồi gọi đó là distributed tracing. Trace context cần có quan hệ span cha/con và được quản lý bởi SDK để backend và dịch vụ phụ thuộc tiếp tục đúng trace.

### 9.1. Chỉ inject context tới origin được phép

Browser instrumentation cần cấu hình danh sách origin hoặc URL được phép nhận trace headers. Không gửi trace context tới mọi domain bên ngoài một cách mặc định. Các header tracing có thể tiết lộ sự liên kết giữa các request và metadata của hệ thống.

Với request same-origin, trình duyệt thường có thể gửi header mà không cần CORS preflight riêng. Với cross-origin request, các header như traceparent, tracestate hoặc baggage có thể khiến trình duyệt gửi preflight OPTIONS. Server phải cho phép header cần thiết trong CORS policy.

Ví dụ cấu hình CORS cần xem xét:

~~~http
Access-Control-Allow-Headers: Content-Type, Authorization, traceparent, tracestate
Access-Control-Expose-Headers: X-Request-ID
~~~

Chỉ cho phép các origin và header cần thiết. Nếu ứng dụng dùng baggage, chỉ thêm header đó khi có yêu cầu cụ thể và chính sách dữ liệu rõ ràng. Không mở CORS rộng chỉ để instrumentation hoạt động.

### 9.2. Response header cho mã hỗ trợ

Backend có thể trả một request reference:

~~~http
X-Request-ID: 8a6d0b3e-4b5a-4e77-9d41-5a71a8c1c123
~~~

JavaScript same-origin có thể đọc response header. Với cross-origin, server cần khai báo X-Request-ID trong Access-Control-Expose-Headers; nếu không, trình duyệt không cho JavaScript đọc header dù nó có mặt trong response.

Giao diện có thể hiển thị mã này khi lỗi xảy ra:

~~~text
Không thể hoàn tất yêu cầu.
Mã hỗ trợ: 8a6d0b3e-4b5a-4e77-9d41-5a71a8c1c123
~~~

Mã hỗ trợ chỉ giúp nhân viên tìm log. Nó không nên chứa email, user ID, token hoặc dữ liệu nghiệp vụ.

## 10. Truyền trace context giữa các dịch vụ HTTP

Khi MVC application gọi dịch vụ phụ thuộc, instrumentation cần tạo client span và inject trace context vào outbound request. Dịch vụ nhận request sẽ trích xuất context và tạo server span con.

Với Spring, OpenTelemetry Java agent hoặc instrumentation tích hợp với HTTP client có thể tự động thực hiện phần lớn việc này. Cách cấu hình phụ thuộc loại client như RestClient, RestTemplate, WebClient hoặc Java HttpClient và phiên bản thư viện.

Nguyên tắc:

- Dùng cùng chuẩn W3C Trace Context giữa các dịch vụ khi có thể.
- Không ghi đè trace context hiện tại bằng một trace mới cho mỗi lời gọi nội bộ.
- Tạo span mới cho mỗi thao tác có ý nghĩa thay vì tái sử dụng span ID.
- Gắn thuộc tính có giá trị chẩn đoán như tên use case, loại dependency và kết quả.
- Không đưa secret hoặc dữ liệu cá nhân vào span attribute.
- Xác minh instrumentation thực sự bao phủ HTTP client đang dùng.

Nếu một dịch vụ bên ngoài không hỗ trợ tracing, ứng dụng vẫn có thể ghi outbound span ở phía client. Trace sẽ cho thấy lời gọi bắt đầu và kết thúc ở đâu, dù không có span server từ hệ thống ngoài.

## 11. Correlation ID trong message và tác vụ bất đồng bộ

Không phải mọi công việc đều hoàn tất trong cùng HTTP request. Ví dụ, Controller gửi message tạo hóa đơn và trả 202 Accepted. Worker xử lý message sau đó. Nếu không truyền context, log của worker sẽ khó liên kết với thao tác khởi phát.

Khi publish message, có thể truyền:

- W3C trace context để consumer tiếp tục distributed trace.
- Business correlation ID để liên kết quy trình nghiệp vụ dài hơn.
- Message ID riêng để định danh một message.
- Causation ID nếu cần biết message/sự kiện nào đã tạo ra message hiện tại.

~~~mermaid
sequenceDiagram
    participant UI as Browser
    participant MVC as MVC Application
    participant Q as Message Broker
    participant W as Background Worker
    participant D as Database

    UI->>MVC: POST /reports
    MVC->>Q: Publish ReportRequested + trace context
    MVC-->>UI: 202 Accepted + request ID
    Q->>W: Deliver message + context
    W->>D: Generate and save report
    D-->>W: Saved
    W->>Q: Publish ReportReady
~~~

Consumer nên tạo span xử lý message và liên kết với context được truyền. Nếu message được xử lý lại, mỗi lần thử có thể có span riêng nhưng vẫn giữ quan hệ với message và quy trình ban đầu.

Với batch consumer xử lý nhiều message trong một lần, không nên gộp tất cả context thành một parent duy nhất nếu quan hệ nhân quả không đúng. Có thể dùng span links để liên kết nhiều trace context nguồn.

## 12. Theo dõi retry và timeout

Retry có thể tạo nhiều lần gọi cùng một dịch vụ. Nếu mỗi lần gọi không được ghi nhận rõ, đội vận hành khó phân biệt một thao tác chậm với nhiều lần thử.

Nên thể hiện:

- Một span cho thao tác nghiệp vụ tổng thể.
- Một client span cho từng lần gọi dependency hoặc mỗi lần retry theo instrumentation.
- Thuộc tính retry attempt hoặc trạng thái kết quả nếu phù hợp.
- Timeout và exception đã được phân loại.
- Idempotency key hoặc business operation ID trong log có kiểm soát nếu cần đối chiếu.

Không đưa idempotency key bí mật hoặc token vào span. Khi timeout xảy ra, không mặc định thao tác ở dịch vụ ngoài chưa được thực hiện. Với thanh toán hoặc tạo tài nguyên, cần kiểm tra trạng thái bằng business ID và thiết kế idempotency riêng.

## 13. Gắn log với trace

Log mô tả sự kiện; trace mô tả đường đi và thời gian của thao tác. Kết hợp hai loại telemetry giúp điều tra hiệu quả hơn.

Một log có cấu trúc có thể gồm:

~~~json
{
  "timestamp": "2026-11-19T10:15:30.123Z",
  "level": "ERROR",
  "service.name": "mvc-order-app",
  "event": "payment.request.failed",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "request_id": "8a6d0b3e-4b5a-4e77-9d41-5a71a8c1c123",
  "order_id": "ORD-2048",
  "error.type": "PaymentTimeout"
}
~~~

Đây là ví dụ schema minh họa. order_id chỉ nên được ghi nếu chính sách dữ liệu cho phép và ID không tiết lộ thông tin nhạy cảm. Không ghi request body, thông tin thẻ, token hoặc session ID chỉ để tăng khả năng tìm kiếm.

Trong môi trường có OpenTelemetry, có thể dùng log instrumentation hoặc logging integration để tự gắn trace ID và span ID vào log. Nếu tự đưa ID vào MDC, cần xác minh context propagation cho thread và tác vụ bất đồng bộ.

## 14. Dùng metrics cùng trace và log

Metrics giúp phát hiện xu hướng ở quy mô hệ thống; trace và log giúp điều tra từng lần xảy ra.

Ví dụ metrics hữu ích:

- Số request theo route template, method và status class.
- Tỷ lệ lỗi theo dependency.
- Độ trễ p50, p95, p99 của use case.
- Số timeout và retry.
- Độ dài hàng đợi và thời gian chờ message.
- Số request đang xử lý.

Không nên dùng trace ID, request ID, user ID hoặc order ID làm label metric. Các giá trị này có cardinality rất cao, có thể làm tăng bộ nhớ và chi phí lưu trữ metrics. Dùng nhãn có tập giá trị giới hạn như route template, service name, operation và status class.

Trace có thể giúp điều tra một điểm bất thường được phát hiện qua metric. Một số hệ thống hỗ trợ exemplars để liên kết điểm dữ liệu metric với trace mẫu.

## 15. Sampling và khả năng tìm lại trace

Hệ thống có lượng request lớn thường không lưu mọi trace ở mức chi tiết như nhau. Sampling quyết định trace nào được thu thập hoặc giữ lại.

Một số cách thường gặp:

- **Head sampling:** quyết định sớm khi trace bắt đầu, dựa trên xác suất hoặc thuộc tính ban đầu.
- **Tail sampling:** quyết định sau khi có thêm dữ liệu, có thể ưu tiên trace lỗi hoặc chậm.
- **Parent-based sampling:** tiếp tục quyết định sampling từ trace context cha theo chính sách.

Sampling giúp kiểm soát chi phí nhưng có thể khiến một request không có trace được lưu đầy đủ. Vì vậy:

- Log vẫn nên có request ID hoặc business correlation ID phù hợp.
- Cấu hình sampling cần ưu tiên hoặc tăng khả năng giữ trace lỗi nếu nền tảng hỗ trợ.
- Không giả định trace ID nào cũng tra được thành trace đầy đủ.
- Theo dõi tỷ lệ dropped spans và lỗi export.
- Chọn retention theo yêu cầu vận hành và chính sách dữ liệu.

Tail sampling cần collector hoặc backend hỗ trợ giữ các span liên quan đủ lâu để đưa ra quyết định; không thể chỉ bật một cờ trong ứng dụng rồi mặc định mọi trace lỗi sẽ được giữ.

## 16. Bảo mật và quyền riêng tư của định danh tương quan

Định danh tương quan hỗ trợ quan sát, không phải dữ liệu xác thực. Dù trace ID thường không chứa thông tin cá nhân trực tiếp, nó vẫn có thể liên kết nhiều sự kiện và tiết lộ cấu trúc giao tiếp của hệ thống.

Các nguyên tắc cần áp dụng:

- Không dùng request ID, trace ID hoặc span ID làm token đăng nhập.
- Không cho phép truy cập log chỉ bằng một trace ID.
- Giới hạn origin được nhận trace headers từ browser.
- Validate correlation ID do client hoặc upstream gửi.
- Không đưa PII, token, mật khẩu hoặc nội dung request vào baggage.
- Giới hạn quyền truy cập telemetry và thời gian lưu.
- Có thể hiển thị request reference cho người dùng, nhưng không cung cấp stack trace hoặc topology nội bộ.
- Làm sạch header trước khi ghi log để tránh log injection.

### 16.1. Cẩn trọng với baggage

W3C Baggage cho phép truyền các cặp key/value qua nhiều dịch vụ. Đây là cách hữu ích để chuyển một số metadata cần thiết, nhưng mỗi giá trị có thể bị gửi qua nhiều ranh giới và xuất hiện trong telemetry.

Chỉ đưa metadata ít nhạy cảm, có kích thước nhỏ và thật sự cần thiết. Không truyền email, số điện thoại, access token, session ID hoặc thông tin thanh toán trong baggage. Nếu cần tham chiếu người dùng, ưu tiên một mã giả danh hóa theo chính sách và tránh gắn vào mọi span khi không cần.

## 17. Xử lý correlation ID không hợp lệ

Nếu ứng dụng nhận X-Correlation-ID từ request, cần có quy tắc rõ:

1. Xác định nguồn nào được tin cậy, chẳng hạn gateway nội bộ đã xác thực.
2. Giới hạn độ dài và tập ký tự.
3. Từ chối hoặc tạo ID mới khi giá trị sai định dạng.
4. Không dùng giá trị đó làm đường dẫn file, tên logger hoặc câu truy vấn.
5. Không để ký tự xuống dòng hoặc ký tự điều khiển đi vào log.
6. Ghi riêng ID upstream và ID nội bộ nếu cần giữ khả năng đối chiếu.

Ví dụ validator đơn giản cho một request reference:

~~~java
private static final Pattern SAFE_REQUEST_ID =
        Pattern.compile("[A-Za-z0-9._-]{1,64}");

private String safeRequestId(String candidate) {
    if (candidate != null
            && SAFE_REQUEST_ID.matcher(candidate).matches()) {
        return candidate;
    }
    return UUID.randomUUID().toString();
}
~~~

Đây chỉ là kiểm tra cú pháp. Nó không xác minh nguồn gửi hoặc tính duy nhất trên toàn hệ thống. Nếu ID đến từ client công khai, cân nhắc luôn tạo ID nội bộ mới và lưu giá trị client gửi ở trường riêng đã được validate.

## 18. Định danh tương quan không thay thế xử lý lỗi

Khi request thất bại, response công khai nên có mã lỗi và thông điệp an toàn. Request ID có thể được trả như mã hỗ trợ để người dùng cung cấp khi liên hệ. Trace ID có thể được ghi trong log và telemetry để điều tra.

Ví dụ response:

~~~json
{
  "code": "PAYMENT_TEMPORARILY_UNAVAILABLE",
  "message": "Chưa thể xác nhận thanh toán. Vui lòng kiểm tra trạng thái đơn.",
  "requestId": "8a6d0b3e-4b5a-4e77-9d41-5a71a8c1c123"
}
~~~

Không trả stack trace, hostname nội bộ hoặc exception message. Nếu người dùng cần hỗ trợ, request ID cho phép nhân viên tra log trong hệ thống đã được phân quyền.

## 19. Kiểm thử luồng tương quan

Không nên chỉ kiểm tra một request có header ID. Cần xác minh ID hoặc trace context đi qua các ranh giới cần thiết.

### 19.1. Kiểm thử request ID tại MVC boundary

- Request không có ID nhận được ID nội bộ hợp lệ.
- Response có header request ID tương ứng.
- Log của request chứa cùng request ID.
- Header sai định dạng không được ghi nguyên văn vào log.
- Request kế tiếp trên cùng thread không thừa hưởng ID cũ.

### 19.2. Kiểm thử distributed trace

- Request inbound tạo server span.
- Outbound HTTP call tạo client span.
- Dịch vụ downstream nhận trace context và tạo span liên quan.
- Trace ID giữ nguyên qua các dịch vụ trong cùng trace.
- Span ID thay đổi theo từng thao tác.
- Parent/child relationship hoặc span link đúng với quan hệ xử lý.

### 19.3. Kiểm thử bất đồng bộ

- Message mang trace context và business correlation ID cần thiết.
- Consumer tạo span cho xử lý message.
- Retry có thể được phân biệt trong telemetry.
- Nhiều message trong batch không bị gán sai quan hệ cha/con.

### 19.4. Kiểm thử bảo mật

- Không có token hoặc PII trong baggage.
- Trace header không cấp quyền truy cập.
- Correlation ID không hợp lệ không thể gây log injection.
- Browser chỉ gửi trace context đến origin được cho phép.
- Response không tiết lộ stack trace hoặc metadata nội bộ.

## 20. Quy trình triển khai từ giao diện tới dịch vụ phụ thuộc

Có thể triển khai theo từng bước:

1. **Chọn quy ước ID:** phân biệt request ID, trace ID, span ID và business correlation ID.
2. **Xác định ranh giới tin cậy:** gateway, browser, MVC application và dịch vụ nội bộ.
3. **Bật tracing instrumentation:** chọn OpenTelemetry SDK/agent hoặc tracing integration phù hợp với stack.
4. **Tích hợp browser/RUM:** chỉ inject trace context tới các origin được phép.
5. **Cấu hình CORS:** cho phép trace headers cần thiết và expose request reference nếu JavaScript cần đọc.
6. **Tích hợp logging:** gắn request ID, trace ID và span ID vào log có cấu trúc.
7. **Truyền context outbound:** xác minh HTTP client và message producer/consumer được instrument.
8. **Bổ sung business correlation:** liên kết các bước nghiệp vụ dài hơn một HTTP request.
9. **Thiết lập sampling và retention:** cân bằng khả năng điều tra với chi phí và quyền riêng tư.
10. **Kiểm thử xuyên ranh giới:** xác minh context, log, response và hành vi khi lỗi hoặc retry.

Không nhất thiết bật browser tracing ngay từ đầu. Có thể bắt đầu từ gateway và MVC server, xác minh outbound propagation, sau đó bổ sung RUM khi có nhu cầu đo trải nghiệm phía trình duyệt.

## 21. Những lỗi thiết kế thường gặp

### Dùng một correlation ID cho mọi người dùng hoặc mọi request

Nếu ID không được tạo theo phạm vi rõ, log của nhiều thao tác có thể bị trộn. Hãy xác định ID đại diện cho request, trace hay business workflow.

### Tự tạo trace ID nhưng không tạo span context

Một UUID trong log không tự trở thành distributed trace. Dùng instrumentation để quản lý trace/span và truyền W3C context.

### Tạo trace mới ở mỗi tầng

Nếu mỗi service tự tạo trace độc lập thay vì tiếp tục context, distributed trace bị chia cắt. Chỉ tạo trace mới khi có ranh giới độc lập có chủ đích; liên kết bằng business correlation hoặc span link khi cần.

### Tin header do client gửi

Header có thể chứa ký tự độc hại hoặc ID giả. Validate và phân biệt nguồn tin cậy với dữ liệu công khai.

### Đưa trace ID vào metric label

Cardinality cao làm metrics backend quá tải. Dùng trace ID trong logs/traces; dùng nhãn có tập giá trị giới hạn cho metrics.

### Dùng baggage để truyền mọi dữ liệu request

Baggage có thể đi qua nhiều dịch vụ và telemetry backend. Chỉ truyền metadata tối thiểu, không nhạy cảm.

### Quên context trong tác vụ async

Thread mới hoặc message consumer có thể mất trace context nếu không truyền qua executor hoặc message headers. Dùng context propagation phù hợp.

### Nghĩ rằng mọi trace đều được lưu

Sampling, lỗi export và retention có thể làm trace không tồn tại đầy đủ. Giữ request ID trong log và giám sát pipeline telemetry.

## 22. Checklist review định danh tương quan

- [ ] Phân biệt rõ request ID, correlation ID, trace ID, span ID và business ID.
- [ ] Có quy ước nơi tạo và nơi tiếp nhận định danh.
- [ ] Dùng W3C Trace Context hoặc chuẩn tracing thống nhất giữa dịch vụ.
- [ ] Browser chỉ inject trace headers tới origin được phép.
- [ ] CORS cho phép đúng request headers và expose response header cần thiết.
- [ ] MVC server, HTTP client và message consumer được instrument.
- [ ] Log có cấu trúc chứa ID cần thiết mà không ghi dữ liệu nhạy cảm.
- [ ] MDC hoặc context được dọn và truyền đúng qua async boundary.
- [ ] Business correlation ID liên kết được quy trình dài hơn một request.
- [ ] Retry và timeout có thể phân biệt trong telemetry.
- [ ] Trace ID không được dùng làm credential hoặc metric label.
- [ ] Baggage không chứa PII, token hoặc secret.
- [ ] Sampling, dropped spans và retention được giám sát.
- [ ] Có test xác minh tương quan từ UI tới dependency và qua tác vụ nền.

## Kết luận

Định danh tương quan giúp nối các sự kiện của một thao tác từ giao diện qua MVC application tới dịch vụ phụ thuộc. Request ID hỗ trợ tìm log tại một ranh giới; correlation ID liên kết một quy trình theo quy ước nghiệp vụ; trace ID và span ID biểu diễn đường đi phân tán theo W3C Trace Context. Hãy dùng instrumentation để truyền context, tích hợp ID vào log, xử lý CORS cho browser, duy trì context qua HTTP và message, đồng thời kiểm soát sampling và dữ liệu nhạy cảm. Khi các ID có ý nghĩa và phạm vi rõ ràng, đội vận hành có thể lần theo request và xác định nơi phát sinh lỗi hoặc độ trễ mà không dùng định danh quan sát như cơ chế bảo mật.
