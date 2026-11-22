# Nhật ký có cấu trúc cho yêu cầu và hành động

Trong ứng dụng MVC, nhật ký (log) giúp nhóm phát triển hiểu request đã đi qua những thành phần nào, thao tác nghiệp vụ nào đã xảy ra và lỗi xuất hiện ở đâu. Khi chỉ ghi các câu tự do như “Request failed” hoặc “Something went wrong”, việc tìm nguyên nhân trong môi trường production rất khó: không biết request nào gây lỗi, người gọi đang thực hiện hành động gì, tài nguyên nào liên quan và các dòng log thuộc cùng một luồng xử lý hay không.

Nhật ký có cấu trúc (structured logging) ghi mỗi sự kiện dưới dạng các trường dữ liệu có tên và kiểu rõ ràng. Thay vì chỉ lưu một chuỗi văn bản, hệ thống ghi event name, timestamp, severity, request ID, trace ID, route, status, thời gian xử lý và các thuộc tính nghiệp vụ cần thiết. Log có thể được xuất thành JSON để hệ thống tập trung dễ lọc, tìm kiếm, tổng hợp và cảnh báo.

Bài học này trình bày cách thiết kế schema log cho ứng dụng MVC, đặt log ở ranh giới request và ca sử dụng, liên kết các sự kiện qua request/trace ID, xử lý context trong luồng bất đồng bộ, bảo vệ dữ liệu nhạy cảm và kiểm thử chất lượng log.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích structured logging và lợi ích so với log dạng câu tự do.
- Thiết kế schema sự kiện có tên trường ổn định.
- Phân biệt request ID, correlation ID, trace ID và span ID.
- Đặt log ở HTTP boundary, application service và các điểm tích hợp.
- Chọn mức log phù hợp và tránh ghi trùng cùng một exception.
- Ghi log JSON trong ứng dụng Java/Spring MVC.
- Truyền MDC context qua executor và xử lý luồng bất đồng bộ.
- Giảm rủi ro lộ PII, token, bí mật và log injection.
- Thiết kế retention, truy cập và kiểm thử log.

## 2. Nhật ký có cấu trúc là gì?

Log truyền thống thường ghi một chuỗi:

~~~text
2026-11-19 10:21:03 ERROR OrderController - Failed to cancel order
~~~

Dòng này cho biết có lỗi nhưng thiếu nhiều thông tin. Người vận hành phải tìm thêm dòng liên quan, đoán ID request hoặc đọc message không theo một định dạng thống nhất.

Structured logging ghi sự kiện thành các trường riêng:

~~~json
{
  "@timestamp": "2026-11-19T10:21:03.412Z",
  "level": "ERROR",
  "service.name": "shop-web",
  "event.name": "order.cancel.failed",
  "message": "Order cancellation failed",
  "request.id": "req-8f1c",
  "trace.id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "http.request.method": "POST",
  "http.route": "/orders/{orderId}/cancel",
  "http.response.status_code": 409,
  "order.id": "order-1042",
  "error.type": "OrderStateException"
}
~~~

Các trường có tên ổn định giúp hệ thống log có thể truy vấn theo event.name, trace.id, http.route hoặc error.type mà không cần phân tích lại câu message.

Structured logging không có nghĩa là nhồi mọi dữ liệu vào JSON. Mỗi sự kiện chỉ nên chứa những thuộc tính cần để trả lời câu hỏi vận hành hoặc điều tra sự cố. Không ghi toàn bộ request body, entity hoặc object graph chỉ vì logger có thể serialize chúng.

### 2.1. So sánh log tự do và log có cấu trúc

| Tiêu chí | Log tự do | Structured logging |
|---|---|---|
| Nội dung | Câu văn tùy ý | Trường có tên và kiểu |
| Tìm kiếm | Thường dựa vào chuỗi | Lọc theo field |
| Tính nhất quán | Dễ khác nhau giữa lớp | Có schema và event name |
| Phân tích | Cần parse message | Có thể tổng hợp trực tiếp |
| Tương quan | Khó nối các dòng | Dùng request ID/trace ID |
| Cảnh báo | Dễ phụ thuộc từ khóa | Dựa vào event, level và thuộc tính |

Message vẫn hữu ích cho con người đọc, nhưng message không nên là nơi duy nhất chứa thông tin quan trọng.

## 3. Schema của một log event

Một event nên có nhóm trường nền tảng và nhóm trường riêng theo nghiệp vụ.

| Nhóm trường | Ví dụ | Mục đích |
|---|---|---|
| Thời gian | @timestamp | Xác định thời điểm sự kiện |
| Mức độ | level | Lọc theo severity |
| Dịch vụ | service.name, environment | Xác định nguồn log |
| Sự kiện | event.name, message | Diễn giải hành động |
| Tương quan | request.id, trace.id, span.id | Nối các sự kiện |
| HTTP | http.request.method, http.route, status_code | Theo dõi request |
| Thời lượng | duration_ms | Phân tích latency |
| Actor/scope | actor.id, tenant.id | Xác định ngữ cảnh đã được phép ghi |
| Nghiệp vụ | order.id, payment.id | Tìm sự kiện liên quan |
| Lỗi | error.type, error.code | Phân loại lỗi |

Tên trường nên thống nhất toàn hệ thống. Nếu một service dùng requestId, service khác dùng req_id, còn service thứ ba dùng correlation, việc truy vấn xuyên hệ thống sẽ khó hơn.

Có thể dùng quy ước nội bộ hoặc một schema chuẩn như Elastic Common Schema (ECS) hay OpenTelemetry semantic conventions. Không nhất thiết phải triển khai toàn bộ schema chuẩn ngay từ đầu; điều quan trọng là chọn một quy ước và giữ ổn định.

### 3.1. Chọn event name có ý nghĩa

Event name mô tả điều đã xảy ra, thường ở dạng danh từ/chủ thể + hành động + kết quả:

- http.request.completed
- order.created
- order.cancel.rejected
- payment.capture.failed
- report.export.started
- report.export.completed

Tránh tên quá chung như event, action, process hoặc error. Tên sự kiện ổn định giúp dashboard và alert không bị vỡ khi câu message thay đổi.

### 3.2. Không đưa dữ liệu biến thiên vào tên event

Không nên tạo event name như order-1042-cancelled hoặc user-42-login. ID phải là field riêng. Nếu ID nằm trong tên event, số lượng loại event tăng liên tục và khó tổng hợp.

## 4. Phân biệt request ID, correlation ID và trace ID

Các mã này liên quan nhưng có phạm vi khác nhau.

- **Request ID:** định danh một request HTTP cụ thể. Mỗi request mới thường có một ID mới.
- **Correlation ID:** định danh một luồng nghiệp vụ hoặc chuỗi tương tác có thể đi qua nhiều request và dịch vụ.
- **Trace ID:** định danh một distributed trace; nhiều span trong các dịch vụ có thể cùng thuộc một trace.
- **Span ID:** định danh một thao tác cụ thể bên trong trace.

Ví dụ người dùng gửi request tạo đơn. Request đi qua gateway, MVC service, payment service và message consumer. Mỗi HTTP request hoặc message handling có thể có span riêng nhưng vẫn nằm trong cùng trace hoặc có liên kết trace tùy cách truyền context.

~~~mermaid
flowchart LR
    Browser["Browser Request<br/>request.id = R1"]
    Gateway["API Gateway<br/>span = S1"]
    MVC["MVC Service<br/>span = S2"]
    Payment["Payment Service<br/>span = S3"]
    Consumer["Message Consumer<br/>span = S4"]

    Browser --> Gateway --> MVC --> Payment
    MVC -. "Message / trace context" .-> Consumer
~~~

Không tự tạo một trace ID ngẫu nhiên thay thế cho distributed tracing nếu ứng dụng đã dùng OpenTelemetry hoặc Micrometer Tracing. Trace context cần được tạo và truyền theo chuẩn, thường là W3C Trace Context (traceparent).

Request ID vẫn hữu ích khi một request không có trace hoặc khi muốn có mã ngắn để đưa vào response header và hỗ trợ người dùng báo lỗi. Correlation ID có thể sống lâu hơn một request, ví dụ xuyên suốt quy trình tạo đơn và xử lý hậu kỳ.

Không tin mù quáng ID do client gửi. Nếu nhận X-Request-ID từ gateway, chỉ chấp nhận khi gateway nằm trong trust boundary và giá trị được kiểm tra độ dài/ký tự. Nếu không, server nên tự tạo ID mới. Không cho client đưa chuỗi tùy ý vào log hoặc response header.

## 5. Đặt log ở đâu trong kiến trúc MVC?

Mỗi tầng nên ghi sự kiện mà nó hiểu rõ, tránh ghi lại cùng một thông tin ở mọi nơi.

~~~mermaid
flowchart TD
    Client["HTTP Client"]
    Filter["Security / Request Filter"]
    Controller["Controller"]
    App["Application Use Case"]
    Domain["Domain Model"]
    Adapter["Repository / External Adapter"]

    Client --> Filter --> Controller --> App
    App --> Domain
    App --> Adapter

    Filter -. "request started/completed context" .-> Log["Structured Log"]
    Controller -. "HTTP mapping outcome" .-> Log
    App -. "business action outcome" .-> Log
    Adapter -. "dependency failure / timing" .-> Log
~~~

### 5.1. HTTP boundary

Ở boundary, log những thông tin liên quan đến request:

- Method và route template.
- Status code.
- Thời lượng.
- Request ID và trace context.
- Kết quả xác thực ở mức tổng quát nếu cần.
- Kích thước request/response nếu có giá trị vận hành.

Không log toàn bộ URL có query string nếu query có thể chứa token, email hoặc dữ liệu cá nhân. Ưu tiên route template như /orders/{orderId} thay cho path thực chứa ID, đặc biệt khi cần giảm cardinality.

Một request hoàn tất thường chỉ cần một event http.request.completed. Request bắt đầu chỉ nên log ở DEBUG hoặc khi có lý do điều tra cụ thể; log cả start và complete ở INFO cho mọi request có thể làm tăng lượng log đáng kể.

### 5.2. Controller

Controller hiểu giao thức và cách ánh xạ request thành response. Có thể log khi:

- Request bị từ chối bởi điều kiện ở boundary.
- Một lỗi đầu vào cần được phân loại.
- Một response có hành vi đặc biệt cần theo dõi.

Không log cùng một sự kiện order created ở Controller, service, repository và domain. Controller không phải nơi tốt nhất để xác định hành động nghiệp vụ đã commit thành công.

### 5.3. Application service / use case

Application hiểu mục tiêu nghiệp vụ. Đây thường là nơi phù hợp để ghi các event như:

- order.created
- order.cancelled
- payment.refund.requested
- report.export.started

Chỉ ghi sự kiện thành công sau khi thao tác đạt trạng thái thành công theo hợp đồng. Nếu log “created” trước khi transaction commit rồi transaction rollback, log sẽ mô tả sai thực tế.

Nếu cần ghi audit event bền vững cùng transaction, dùng audit store hoặc transactional outbox phù hợp; không coi một dòng log INFO là bằng chứng giao dịch đã commit.

### 5.4. Repository và adapter

Adapter có thể ghi log về lỗi kết nối, timeout hoặc một truy vấn bất thường. Không nên ghi mọi câu SQL và mọi bản ghi ở INFO. Việc ghi SQL chi tiết có thể được bật tạm thời ở môi trường phát triển hoặc khi điều tra, với chính sách che dữ liệu nhạy cảm.

Một query bình thường không nhất thiết cần một log event riêng nếu đã có tracing, metrics hoặc log request đủ thông tin. Tránh lặp lại cùng lỗi ở adapter, service và Controller với ba stack trace giống nhau.

## 6. Chọn mức log phù hợp

Mức log giúp phân loại mức độ cần chú ý.

| Level | Khi dùng | Ví dụ |
|---|---|---|
| TRACE | Chi tiết rất nhỏ, thường chỉ bật tạm thời | Bước nội bộ của thuật toán |
| DEBUG | Thông tin hỗ trợ phát triển/điều tra | Nhánh xử lý hoặc tham số đã được làm sạch |
| INFO | Sự kiện bình thường có ý nghĩa vận hành | Request hoàn tất, đơn được tạo |
| WARN | Tình huống bất thường nhưng hệ thống còn xử lý được | Retry thành công, dữ liệu đầu vào bị từ chối |
| ERROR | Thao tác thất bại cần điều tra hoặc can thiệp | Không thể lưu đơn do lỗi database |

Không dùng ERROR cho mọi response 4xx. Người dùng gửi dữ liệu sai hoặc thiếu quyền có thể là tình huống dự kiến; thường phù hợp với INFO hoặc WARN tùy mức độ và chính sách bảo mật.

Một lỗi 5xx không nhất thiết phải được log ở mọi tầng. Chọn một nơi có đủ ngữ cảnh để ghi stack trace một lần, sau đó các tầng khác có thể bổ sung event có mã lỗi hoặc kết quả mà không lặp stack trace.

### 6.1. Không dùng level thay cho event type

WARN nói mức độ; order.cancel.rejected nói điều gì xảy ra. Cả hai đều cần thiết. Một request bị từ chối vì người dùng không có quyền có thể là INFO hoặc WARN theo chính sách vận hành, nhưng event name vẫn mô tả chính xác kết quả.

## 7. Ghi structured log trong Java

Với SLF4J 2.x, fluent API cho phép gắn key-value vào log event:

~~~java
log.atInfo()
    .addKeyValue("event.name", "order.cancelled")
    .addKeyValue("order.id", order.id().value())
    .addKeyValue("actor.id", actor.id())
    .addKeyValue("tenant.id", actor.tenantId())
    .log("Order cancelled");
~~~

Các field được lưu riêng thay vì chỉ nối vào chuỗi message. Cần chọn các field có kiểu đơn giản và có ý nghĩa. Không truyền toàn bộ actor, order hoặc entity vào logger vì serializer có thể ghi quá nhiều dữ liệu hoặc gọi getter gây tác dụng phụ.

Nếu dự án dùng SLF4J phiên bản cũ hơn, có thể dùng structured argument do encoder hỗ trợ hoặc facade nội bộ. Tránh tự ghép JSON bằng chuỗi vì dễ sai escaping và kiểu dữ liệu.

### 7.1. Ghi exception

Khi một thao tác thất bại:

~~~java
try {
    paymentGateway.capture(command.paymentId());
} catch (PaymentGatewayException exception) {
    log.atError()
        .addKeyValue("event.name", "payment.capture.failed")
        .addKeyValue("payment.id", command.paymentId())
        .addKeyValue("error.type", exception.getClass().getSimpleName())
        .log("Payment capture failed", exception);

    throw new PaymentCaptureFailedException(exception);
}
~~~

Chỉ ghi exception ở đây nếu adapter là nơi phù hợp nhất để sở hữu lỗi và có đủ ngữ cảnh. Nếu exception sẽ được log ở exception handler cấp cao hơn, adapter có thể chỉ chuyển đổi hoặc bổ sung thông tin mà không ghi stack trace thêm lần nữa.

Không ghi exception.getMessage() vào field công khai một cách mặc định. Message có thể chứa SQL, URL nội bộ, dữ liệu request hoặc thông tin xác thực. Stack trace cần được bảo vệ như dữ liệu vận hành nhạy cảm.

## 8. Gắn request ID vào MDC

MDC (Mapped Diagnostic Context) của SLF4J cho phép gắn một số field vào ngữ cảnh của thread. Logback hoặc encoder có thể đưa các field này vào từng log event mà không cần truyền request ID qua mọi lời gọi logger.

Một filter có thể tạo request ID và đặt vào MDC:

~~~java
@Component
public class RequestIdFilter extends OncePerRequestFilter {
    private static final String REQUEST_ID = "request_id";
    private static final String REQUEST_ID_ATTRIBUTE =
        RequestIdFilter.class.getName() + ".requestId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String requestId = (String) request.getAttribute(REQUEST_ID_ATTRIBUTE);
        if (requestId == null) {
            requestId = UUID.randomUUID().toString();
            request.setAttribute(REQUEST_ID_ATTRIBUTE, requestId);
        }
        String previous = MDC.get(REQUEST_ID);

        response.setHeader("X-Request-ID", requestId);
        MDC.put(REQUEST_ID, requestId);

        try {
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove(REQUEST_ID);
            } else {
                MDC.put(REQUEST_ID, previous);
            }
        }
    }

    @Override
    protected boolean shouldNotFilterAsyncDispatch() {
        return false;
    }
}
~~~

Ví dụ này luôn tạo ID mới ở server. Nếu hệ thống cần nhận ID từ gateway tin cậy, hãy kiểm tra format và độ dài trước khi dùng; không chấp nhận header tùy ý từ Internet. Cần đăng ký filter đúng vị trí trong chuỗi filter và kiểm tra thứ tự với Spring Security.

OncePerRequestFilter mặc định có hành vi riêng với async dispatch; ví dụ override để filter chạy lại ở lần dispatch bất đồng bộ và gắn MDC cho thread xử lý dispatch đó. Tuy nhiên, nó không tự truyền MDC vào worker thread đang thực thi tác vụ async trước khi dispatch hoàn tất.

Request ID được lưu trong request attribute để lần async dispatch dùng lại cùng ID, thay vì tạo ID mới cho cùng một HTTP request. Mỗi request HTTP độc lập vẫn nhận một ID riêng.

MDC dựa trên ThreadLocal. Luôn xóa hoặc khôi phục giá trị trong finally, vì servlet thread được tái sử dụng cho request khác. Nếu không dọn context, log của request sau có thể mang nhầm request ID.

## 9. Ghi log khi có async task và background job

Khi công việc chạy trên thread khác, MDC không tự động đi theo. Nếu dùng executor, có thể chụp context lúc submit và khôi phục trong worker.

~~~java
public class MdcTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> submittedContext = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previousContext = MDC.getCopyOfContextMap();

            try {
                if (submittedContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(submittedContext);
                }

                task.run();
            } finally {
                if (previousContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previousContext);
                }
            }
        };
    }
}
~~~

Đăng ký decorator với executor:

~~~java
@Bean
ThreadPoolTaskExecutor applicationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(24);
    executor.setQueueCapacity(200);
    executor.setTaskDecorator(new MdcTaskDecorator());
    executor.setThreadNamePrefix("application-");
    return executor;
}
~~~

Các giá trị pool chỉ là ví dụ. Với CompletableFuture, cần truyền executor đã cấu hình thay vì dùng common pool mặc định nếu muốn kiểm soát context và tài nguyên.

Với job tồn tại lâu hơn request ban đầu, không nên chỉ dựa vào request ID. Lưu job.id, correlation.id và trace context phù hợp trong metadata/message. Khi worker bắt đầu, dựng lại context từ message đã xác thực và xóa nó sau khi xử lý. Không giữ toàn bộ MDC map của request trong một job kéo dài nếu các field đó đã lỗi thời hoặc không cần thiết.

Nếu dùng Reactor/WebFlux, execution có thể đổi thread liên tục; MDC dựa trên ThreadLocal không tự hoạt động như trong mô hình thread-per-request. Dùng Reactor Context và tích hợp tracing/logging tương ứng thay vì giả định MDC luôn hiện diện.

## 10. Kết hợp log với distributed tracing

Log trả lời “đã xảy ra điều gì?”; trace trả lời “một request đi qua những thành phần nào và mất thời gian ở đâu?”; metrics trả lời “điều đó xảy ra bao nhiêu lần và xu hướng ra sao?”.

| Tín hiệu | Dùng để trả lời |
|---|---|
| Logs | Sự kiện, lỗi, ngữ cảnh và kết quả cụ thể |
| Metrics | Tỷ lệ, số lượng, latency phân vị, mức sử dụng |
| Traces | Đường đi và thời lượng từng span qua nhiều dịch vụ |
| Audit records | Ai thực hiện hành động quan trọng, trên đối tượng nào và kết quả ra sao |

Trong Spring Boot, Micrometer Observation/Tracing hoặc OpenTelemetry có thể tạo và truyền trace context. Khi được cấu hình, traceId và spanId có thể xuất hiện trong MDC hoặc log exporter. Không nên tự tạo các field này độc lập với tracing SDK vì chúng sẽ không khớp trace backend.

Ví dụ log có thể chứa:

~~~json
{
  "event.name": "inventory.reserve.completed",
  "request.id": "req-2d4a",
  "trace.id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span.id": "00f067aa0ba902b7",
  "inventory.item_id": "sku-100",
  "duration_ms": 18,
  "outcome": "success"
}
~~~

Không ghi trace baggage hoặc metadata tùy ý mà chưa đánh giá dữ liệu nhạy cảm và cardinality. Trace sampling cũng có nghĩa không phải mọi request đều có trace đầy đủ; request ID và log event vẫn có thể hữu ích khi trace không được lấy mẫu.

## 11. Cấu hình JSON logging

Logback có thể dùng encoder JSON để xuất mỗi event thành một dòng JSON. Một cấu hình tối giản với logstash-logback-encoder có dạng:

~~~xml
<configuration>
    <appender name="JSON_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="JSON_CONSOLE"/>
    </root>
</configuration>
~~~

Dự án cần khai báo dependency encoder tương ứng và cấu hình logback-spring.xml phù hợp. Encoder có thể đưa timestamp, level, logger, thread, MDC và structured arguments vào JSON.

Không cần tự serialize log event trong từng lớp. Hãy để logging backend định dạng output nhất quán cho toàn ứng dụng.

### 11.1. Ví dụ output

Một event được ghi bằng SLF4J fluent API có thể được xuất thành:

~~~json
{
  "@timestamp": "2026-11-19T10:21:03.412Z",
  "level": "INFO",
  "logger_name": "com.example.order.CancelOrderService",
  "thread_name": "http-nio-8080-exec-4",
  "request_id": "7e2c0c52-8c2a-4d5e-8f1c-1b0f0a2d7c11",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "event.name": "order.cancelled",
  "order.id": "order-1042",
  "actor.id": "user-42",
  "tenant.id": "tenant-7",
  "message": "Order cancelled"
}
~~~

Field chính xác phụ thuộc encoder và cấu hình. Hãy kiểm tra output thật trong môi trường phát triển để bảo đảm MDC và key-value được xuất thành field riêng, không bị gộp vào một chuỗi message.

## 12. Log request hoàn tất mà không lộ dữ liệu

HTTP access log nên ưu tiên route template, method, status và duration. Không nên log toàn bộ request target hoặc body mặc định.

Một HandlerInterceptor có thể ghi thời lượng và route sau khi handler hoàn tất:

~~~java
@Component
public class RequestLoggingInterceptor implements HandlerInterceptor {
    private static final String START =
        RequestLoggingInterceptor.class.getName() + ".start";

    private static final Logger log =
        LoggerFactory.getLogger(RequestLoggingInterceptor.class);

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        if (request.getAttribute(START) == null) {
            request.setAttribute(START, System.nanoTime());
        }
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {

        Object started = request.getAttribute(START);
        long durationMs = started instanceof Long value
            ? TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - value
            )
            : -1L;

        Object pattern = request.getAttribute(
            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE
        );

        String route = pattern == null ? "unmatched" : pattern.toString();

        log.atInfo()
            .addKeyValue("event.name", "http.request.completed")
            .addKeyValue("http.request.method", request.getMethod())
            .addKeyValue("http.route", route)
            .addKeyValue("http.response.status_code", response.getStatus())
            .addKeyValue("duration_ms", durationMs)
            .log("HTTP request completed");
    }
}
~~~

Interceptor cần được đăng ký qua WebMvcConfigurer. Với async MVC, Spring gọi callback phù hợp cho vòng dispatch bất đồng bộ; cần kiểm thử để chỉ ghi một event hoàn tất sau khi request thực sự kết thúc. Không ghi completion ở lần dispatch ban đầu nếu request vẫn đang xử lý async.

http.route nên là pattern như /orders/{orderId}. Không dùng raw path có ID hoặc query string làm nhãn metric hay field có cardinality không kiểm soát. Nếu request không khớp handler, dùng route marker an toàn như unmatched.

Không log body, cookie, authorization header hoặc session ID. Nếu cần chẩn đoán payload, chỉ ghi các field allowlist đã được làm sạch và chỉ bật trong phạm vi, thời gian được kiểm soát.

## 13. Bảo vệ dữ liệu nhạy cảm và chống log injection

Log có thể chứa dữ liệu nhạy cảm và thường được sao chép sang nhiều hệ thống. Hãy xem log là một kho dữ liệu cần được bảo vệ.

Không ghi:

- Password, access token, refresh token, API key hoặc cookie.
- Authorization header hoặc session identifier.
- Số thẻ thanh toán, CVV hoặc thông tin xác thực.
- Toàn bộ request/response body theo mặc định.
- Dữ liệu cá nhân không cần thiết như địa chỉ, số điện thoại hoặc email đầy đủ.
- SQL chứa literal nhạy cảm hoặc thông tin kết nối.

Nếu cần định danh người dùng, ưu tiên ID nội bộ hoặc giá trị đã pseudonymize theo chính sách. Không dùng email hoặc số điện thoại làm field định danh mặc định.

### 13.1. Redaction và allowlist

Ưu tiên allowlist field được phép log thay vì cố gắng che mọi trường nhạy cảm sau khi serialize object lớn. Ví dụ:

~~~java
log.atInfo()
    .addKeyValue("event.name", "profile.updated")
    .addKeyValue("actor.id", actor.id())
    .addKeyValue("profile.id", profile.id())
    .addKeyValue("changed_fields", List.of("displayName", "timezone"))
    .log("Profile updated");
~~~

Chỉ ghi tên trường thay đổi, không ghi giá trị cũ/mới nếu không có nhu cầu rõ ràng. Nếu buộc phải ghi một phần dữ liệu, cần có chính sách masking đã được kiểm thử.

### 13.2. Log injection

Nếu dữ liệu do người dùng kiểm soát được chèn trực tiếp vào log message, ký tự newline hoặc ký tự điều khiển có thể làm giả nhiều dòng log hoặc phá cấu trúc parser.

Dùng structured field với encoder JSON đúng chuẩn, giới hạn độ dài và làm sạch chuỗi đầu vào. Không nối raw user input vào message. JSON encoder xử lý escaping ký tự, nhưng vẫn cần kiểm soát dữ liệu và kích thước.

### 13.3. Không log thông tin bí mật trong exception

Một exception từ HTTP client có thể chứa URL, query parameter hoặc header. Exception message từ database có thể chứa câu SQL và giá trị. Hãy chọn loại exception và metadata an toàn để ghi; stack trace đầy đủ chỉ được truy cập bởi người có quyền vận hành phù hợp.

## 14. Operational log, audit log và metric

Không dùng một loại log cho mọi mục đích.

- **Operational log:** hỗ trợ vận hành và gỡ lỗi; có thể có sampling, retention ngắn hơn và mức chi tiết thay đổi theo môi trường.
- **Audit log:** ghi lại hành động quan trọng cần truy vết, như thay đổi quyền, duyệt giao dịch hoặc truy cập dữ liệu nhạy cảm. Cần tính toàn vẹn, quyền truy cập và retention theo yêu cầu chính sách.
- **Metric:** số liệu tổng hợp như request count, error rate, latency histogram và queue size. Không nên dùng metric label có user ID hoặc order ID vì cardinality sẽ tăng không giới hạn.

Một event order.cancelled trong operational log giúp tìm lỗi. Nếu hệ thống cần bằng chứng ai đã hủy đơn, audit record nên được lưu ở cơ chế bền vững và có kiểm soát riêng. Log ứng dụng có thể bị rotate, sampling hoặc mất khi hệ thống gặp sự cố nên không thay thế audit store.

## 15. Retention, truy cập và chi phí

Log có cấu trúc giúp tìm kiếm dễ hơn nhưng cũng có thể tạo lượng dữ liệu lớn. Cần định nghĩa:

- Log nào được giữ bao lâu.
- Môi trường nào được phép ghi DEBUG/TRACE.
- Ai được đọc log có dữ liệu nhạy cảm.
- Cách mã hóa khi truyền và lưu trữ.
- Cách xóa hoặc ẩn danh dữ liệu theo chính sách.
- Giới hạn kích thước event và tốc độ ingest.
- Cách sampling hoặc giảm log lặp khi có sự cố lớn.

Không nên bật DEBUG toàn hệ thống trong production vô thời hạn. Một lỗi lặp lại hàng nghìn lần có thể tạo log storm, làm tăng chi phí và khiến sự kiện quan trọng bị chìm. Dùng rate limit, sampling có chủ đích hoặc log một lần theo chu kỳ khi phù hợp; không loại bỏ các sự kiện audit bắt buộc.

## 16. Kiểm thử structured logging

Log là một phần của khả năng vận hành nên cần kiểm thử ở mức phù hợp.

### 16.1. Kiểm tra event và field

Có thể dùng appender test hoặc ListAppender của Logback để thu log event, sau đó kiểm tra:

- Event name đúng.
- Field bắt buộc có mặt.
- Request ID/trace ID được gắn đúng.
- Không có token hoặc dữ liệu bị cấm.
- Exception được ghi ở đúng nơi.
- Mức log phù hợp.

Không nên kiểm tra toàn bộ câu message nếu nó có thể thay đổi vì lý do diễn đạt. Ưu tiên event name và field ổn định.

### 16.2. Kiểm tra MDC được dọn

Gửi hai request liên tiếp qua cùng executor/thread pool và xác nhận request ID của request thứ nhất không xuất hiện trong log của request thứ hai. Đây là test quan trọng vì thread được tái sử dụng.

### 16.3. Kiểm tra async propagation

Tạo một tác vụ qua executor có TaskDecorator và xác nhận request/correlation ID được giữ trong worker. Sau khi task hoàn tất, xác nhận MDC của worker được khôi phục hoặc xóa để không rò context sang task tiếp theo.

### 16.4. Kiểm tra dữ liệu nhạy cảm

Dùng fixture có token giả, email và dữ liệu bí mật; xác nhận chúng không xuất hiện trong serialized log. Test này giúp phát hiện khi một DTO mới vô tình được log toàn bộ.

### 16.5. Kiểm tra định dạng JSON

Trong integration test hoặc kiểm tra cấu hình logging, parse một dòng output và xác nhận đó là JSON hợp lệ, timestamp và level đúng, các key-value nằm ở field riêng. Không chỉ kiểm tra log bằng mắt.

## 17. Những lỗi thiết kế thường gặp

### Chỉ ghi message tự do

Message không có field ổn định khiến việc tìm kiếm và tổng hợp phụ thuộc vào nội dung câu chữ. Đặt event name và thuộc tính riêng.

### Ghi log ở mọi tầng

Một exception bị log ở adapter, service, Controller và global handler sẽ tạo nhiều stack trace giống nhau. Chọn một nơi sở hữu việc ghi lỗi đầy đủ.

### Dùng request ID thay cho trace ID

Request ID chỉ định danh một request; nó không tự mô tả các span qua nhiều dịch vụ. Dùng tracing context chuẩn khi cần distributed trace.

### Để MDC rò giữa các request

Không xóa ThreadLocal trong finally khiến thread được tái sử dụng mang context cũ. Luôn khôi phục hoặc xóa.

### Giả định MDC tự truyền qua async

Executor hoặc reactive pipeline có thể đổi thread. Cần TaskDecorator, context propagation hoặc cơ chế phù hợp với runtime.

### Ghi toàn bộ request body và entity

Việc này có thể lộ PII, token, bí mật và tạo log rất lớn. Chọn field allowlist.

### Log ID vào metric label

ID duy nhất tạo cardinality cao và làm hệ thống metric tốn tài nguyên. Dùng ID trong log/trace; metric dùng label có tập giá trị giới hạn.

### Dùng operational log làm audit trail

Log có thể bị rotate, sampling hoặc chỉnh sửa bởi người có quyền hệ thống. Hành động cần bằng chứng phải có audit store và chính sách toàn vẹn riêng.

### Không kiểm tra JSON output thực tế

Một cấu hình logger có thể chỉ in key-value vào message thay vì field riêng. Hãy parse output thực tế trong môi trường tích hợp.

## 18. Quy trình thiết kế structured logging

Khi thêm log cho một chức năng MVC, hãy thực hiện theo trình tự:

1. **Xác định câu hỏi vận hành.** Cần biết request nào, hành động nào, kết quả gì hoặc phụ thuộc nào thất bại?
2. **Đặt event name.** Dùng tên ổn định mô tả sự kiện đã xảy ra.
3. **Chọn field.** Timestamp, level, service, request/trace ID, route, actor/resource ID và duration khi cần.
4. **Chọn boundary sở hữu event.** HTTP boundary ghi kết quả request; application ghi hành động nghiệp vụ; adapter ghi lỗi tích hợp đặc thù.
5. **Chọn level.** Không dùng ERROR cho mọi trường hợp dự kiến.
6. **Truyền context.** Dùng tracing context và request/correlation ID; propagate qua executor hoặc message.
7. **Giới hạn dữ liệu.** Allowlist, redaction, giới hạn độ dài và không ghi bí mật.
8. **Xuất JSON nhất quán.** Dùng encoder và schema ổn định.
9. **Đặt retention và quyền đọc.** Bảo vệ log như dữ liệu vận hành.
10. **Kiểm thử.** Xác nhận field, JSON, MDC cleanup, async propagation và không rò dữ liệu nhạy cảm.

Trước khi hoàn thành, hãy tự hỏi:

- Có thể lọc log theo event name, request ID và trace ID không?
- Tên route có dùng template thay vì URL chứa dữ liệu biến thiên không?
- Một hành động nghiệp vụ có bị log lặp ở nhiều tầng không?
- Exception có được ghi stack trace đúng một lần không?
- MDC có được dọn sau request và task không?
- Context có được truyền qua executor hoặc message không?
- Có token, PII hoặc body nhạy cảm trong log không?
- Audit event có được lưu bằng cơ chế bền vững phù hợp không?
- JSON output có thể parse và truy vấn bằng field riêng không?

## 19. Kết luận

Structured logging biến log từ những câu văn khó tìm kiếm thành các sự kiện có schema rõ ràng. Trong ứng dụng MVC, HTTP boundary ghi thông tin request; application service ghi kết quả hành động nghiệp vụ; adapter ghi lỗi hoặc tình trạng phụ thuộc. Request ID, correlation ID và trace context giúp nối các sự kiện qua nhiều thread và dịch vụ.

Một hệ thống log hữu ích cần schema ổn định, level hợp lý, JSON output, context propagation và chính sách bảo vệ dữ liệu. Luôn dọn MDC, tránh ghi bí mật, không log trùng exception và không dùng operational log thay audit store. Kết hợp log với metrics và traces giúp nhóm vận hành tìm nguyên nhân sự cố nhanh hơn mà vẫn kiểm soát được chi phí và rủi ro dữ liệu.

