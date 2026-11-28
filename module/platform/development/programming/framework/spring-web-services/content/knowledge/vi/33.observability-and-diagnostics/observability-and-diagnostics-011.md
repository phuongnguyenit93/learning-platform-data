# Định danh tương quan và quy trình thu bằng chứng mà không làm lộ bí mật

## 1. Vì sao SOAP service cần định danh tương quan?

Trong module **SPRING_WEB_SERVICES**, một operation SOAP có thể đi qua reverse proxy, servlet container, Spring-WS MessageDispatcher, endpoint interceptor, JAXB marshaller, application service, database và nhiều hệ thống đối tác. Khi lỗi xảy ra, một dòng log riêng lẻ hiếm khi đủ để xác định request bắt đầu từ đâu, qua những tầng nào và dừng tại đâu.

Định danh tương quan giúp nối các sự kiện thuộc cùng một luồng xử lý mà không cần ghi toàn bộ SOAP Envelope. Khi client gửi request, server có thể tiếp nhận hoặc tạo correlation ID; trace context có thể nối các service qua HTTP; các span ghi thời gian từng bước; còn application log ghi operation, kết quả mapping, fault category và dependency outcome.

Tuy nhiên, observability không phải lý do để thu thập mọi dữ liệu. SOAP Header có thể chứa UsernameToken, chữ ký, certificate reference; SOAP Body có thể chứa thông tin khách hàng, tài chính hoặc dữ liệu nhạy cảm; attachment có thể chứa tài liệu riêng tư. Log raw request để “dễ debug” có thể biến hệ thống log thành nơi rò rỉ bí mật.

Bài học này xây dựng quy trình thu bằng chứng có thể điều tra, đối chiếu và kiểm toán, đồng thời giảm thiểu dữ liệu nhạy cảm:

1. Tạo và truyền correlation ID ổn định qua các tầng.
2. Dùng trace ID/span ID để quan sát đường đi và thời gian xử lý.
3. Ghi log có cấu trúc với các trường hữu ích nhưng có giới hạn.
4. Redact hoặc loại bỏ secrets trước khi dữ liệu tới log/trace.
5. Thu thập SOAP metadata, Fault và payload evidence theo nguyên tắc tối thiểu.
6. Bảo toàn bằng chứng incident với timestamp, source, access control và integrity.
7. Điều tra có thứ tự, ghi lại giả thuyết và phân biệt sự thật đã xác minh với suy đoán.
8. Kiểm thử logging/redaction để ngăn bí mật xuất hiện trở lại.

### Mục tiêu học tập

Sau bài thuộc chương **Quan sát và chẩn đoán**, bạn có thể:

- Phân biệt correlation ID, trace ID, span ID, message ID và business identifier.
- Thiết kế correlation context cho HTTP, SOAP Header, asynchronous message và retry.
- Tích hợp MDC/log context và OpenTelemetry tracing trong Java/Spring.
- Chọn trường log đủ để điều tra nhưng không ghi raw credentials, token hoặc payload nhạy cảm.
- Redact dữ liệu ở đúng ranh giới trước khi serialize log/trace.
- Thu thập SOAP Fault, QName, action, kích thước payload và timing an toàn.
- Thiết kế evidence bundle có nguồn gốc, timestamp, quyền truy cập và integrity.
- Xây dựng incident timeline, kiểm tra redaction và quy trình phản ứng khi secrets bị lộ.

## 2. Phân biệt các định danh thường gặp

Các định danh sau có mục đích khác nhau. Không nên dùng một trường duy nhất thay cho tất cả.

| Định danh | Phạm vi | Mục đích | Có thể chứa thông tin cá nhân? |
| --- | --- | --- | --- |
| Correlation ID | Một business interaction/request chain | Nối log giữa client, SOAP service và dependency | Không nên |
| Trace ID | Một distributed trace | Nhóm các span trong toàn luồng quan sát | Không nên |
| Span ID | Một operation/span trong trace | Xác định một đoạn xử lý cụ thể | Không nên |
| SOAP Message ID | Một message theo contract/WS-Addressing | Nhận diện message SOAP | Có thể liên kết tới transaction; kiểm soát như metadata |
| Idempotency key | Một business command | Ngăn thực hiện side effect trùng lặp | Có thể nhạy cảm nếu thiết kế kém |
| Business ID | Order/customer/invoice/partner | Nhận diện đối tượng nghiệp vụ | Thường có thể nhạy cảm |
| HTTP request ID | Một HTTP request tại gateway/server | Nối access log và application log | Không nên |

### 2.1. Correlation ID

Correlation ID là định danh do hệ thống tạo hoặc tiếp nhận theo policy để nối sự kiện thuộc một business interaction. Ví dụ request hủy đơn ORD-1001 được gateway gán correlation ID c-7f4e4a9d; SOAP service, inventory client và event consumer ghi cùng giá trị đó.

Correlation ID nên có entropy đủ cao, không tuần tự dễ đoán; có format/length cố định và giới hạn; không chứa email, username, order ID, tenant name hoặc thông tin do người dùng nhập; không được dùng làm authorization credential; không được tin nguyên vẹn nếu client có thể tự gửi; và có TTL/retention phù hợp với log retention.

Nếu client gửi X-Correlation-ID, server cần validate length/character set, loại giá trị bất thường và có thể tạo ID mới. Chính sách cần tránh collision và log injection. Giá trị do client cung cấp chỉ là metadata tương quan, không phải bằng chứng identity.

### 2.2. Trace ID và span ID

Distributed tracing dùng trace ID để liên kết các span. Mỗi span có span ID riêng, cùng parent span ID để thể hiện quan hệ cha/con.

~~~text
Trace: 4bf92f3577b34da6a3ce929d0e0e4736
  ├── gateway.http.server       span=01
  ├── orders.soap.server        span=02 parent=01
  │    ├── ws.security.validate span=03 parent=02
  │    ├── order.endpoint       span=04 parent=02
  │    └── inventory.http       span=05 parent=04
  └── order.outbox.publish      span=06 parent=02
~~~

Trace ID giúp tìm một distributed trace; correlation ID có thể tồn tại độc lập để phục vụ business interaction qua các hệ thống không hỗ trợ tracing. Có thể gắn correlation ID như span attribute hoặc log field, nhưng không tự nhét trace ID vào một nơi không tuân W3C Trace Context.

### 2.3. SOAP Message ID không phải correlation ID

WS-Addressing MessageID nhận diện một message. Khi gửi reply, RelatesTo có thể liên kết response message với request. Retry có thể tạo message ID mới nhưng vẫn thuộc cùng business interaction. Với async workflow, một correlation ID có thể nối nhiều SOAP messages, events và retry attempts.

Không sử dụng MessageID làm idempotency key nếu semantics contract không bảo đảm. Hai message có MessageID khác nhau vẫn có thể đại diện cùng một command.

## 3. Thiết kế correlation context xuyên các tầng

### 3.1. Luồng tổng quát

~~~mermaid
sequenceDiagram
    participant C as SOAP client
    participant G as API gateway
    participant S as Spring-WS service
    participant E as Endpoint / application service
    participant D as Downstream
    participant Q as Async consumer
    C->>G: HTTP + SOAP, optional correlation metadata
    G->>G: Validate or generate correlation ID
    G->>S: Forward request + trace context + correlation ID
    S->>S: Establish diagnostic context
    S->>E: Dispatch SOAP operation
    E->>D: Outbound call with propagated context
    D-->>E: Response / error
    E-->>S: Result
    S->>Q: Publish event with correlation metadata
    Q->>Q: Restore context for message processing
    S-->>G: SOAP response / Fault
    G-->>C: HTTP response
~~~

Gateway có thể tạo correlation ID nếu request chưa có giá trị hợp lệ. Nếu client cần biết ID để cung cấp khi support, response có thể trả ID này qua HTTP response header và/hoặc application SOAP Header được contract quy định. Không tự ý thêm Header tùy tiện nếu client interoperability phụ thuộc WSDL/WS-Policy.

### 3.2. Context phải được làm sạch

Thread pool tái sử dụng thread. Nếu MDC hoặc ThreadLocal không được xóa, request kế tiếp có thể ghi log với correlation ID của request trước.

~~~java
String previous = MDC.get("correlation_id");
try {
    MDC.put("correlation_id", validatedCorrelationId);
    filterChain.doFilter(request, response);
} finally {
    if (previous == null) {
        MDC.remove("correlation_id");
    } else {
        MDC.put("correlation_id", previous);
    }
}
~~~

Đây là pattern cho servlet filter; cần quyết định rõ có cho phép context lồng nhau hay không. Trong filter top-level bình thường, clear toàn bộ MDC có thể phù hợp nếu ứng dụng kiểm soát mọi keys; nếu filter khác dùng chung MDC, chỉ restore/remove key do mình sở hữu.

Với async tasks, MDC không tự động truyền qua thread pool. Phải capture context khi submit, restore lúc chạy và clear sau khi hoàn tất. Tránh copy toàn bộ request context có thể chứa dữ liệu nhạy cảm.

### 3.3. Không lấy identity từ correlation metadata

Correlation ID, traceparent và baggage không chứng minh caller là ai hoặc có quyền gì. Authentication principal phải đến từ cơ chế xác thực đã kiểm chứng; authorization phải dựa trên verified identity/authorities. Không đặt user ID hoặc role vào correlation ID để service sau tin tưởng.

## 4. Truyền trace context theo W3C Trace Context

### 4.1. HTTP headers

Các service HTTP hiện đại có thể truyền:

- traceparent: version, trace ID, parent ID và trace flags;
- tracestate: vendor-specific tracing state theo chuẩn;
- baggage: các key/value metadata được truyền tiếp nếu policy cho phép.

Ví dụ định dạng traceparent:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Không tự parse/ghép chuỗi traceparent để tạo trace ID. Dùng OpenTelemetry propagator hoặc tracing instrumentation. Giá trị không hợp lệ cần được xử lý theo propagator; không tin flags do caller gửi để cấp quyền hay bỏ qua security policy.

### 4.2. SOAP qua HTTP

SOAP thường đi qua HTTP, do đó trace context có thể được inject/extract tại HTTP transport layer giống request HTTP khác. Nhưng Spring-WS WebServiceTemplate dùng WebServiceMessageSender; mức độ tự động propagation phụ thuộc OpenTelemetry agent/instrumentation và HTTP client implementation.

Hãy kiểm tra client HTTP sender được instrument; gateway giữ hoặc thay parent context đúng policy; servlet server instrumentation extract inbound context; WebServiceTemplate outbound call tạo child span; không có custom interceptor xóa hoặc ghi đè trace context ngoài ý muốn.

Không mặc định SOAP action hoặc QName tự tạo trace span. Cần instrumentation ở server/transport hoặc application layer.

### 4.3. SOAP Header cho correlation ID

Nếu contract yêu cầu correlation ID nằm trong SOAP Header, dùng namespace riêng đã version hóa:

~~~xml
<soap:Header
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:diag="https://example.com/diagnostics/v1">
    <diag:CorrelationId>c-7f4e4a9d</diag:CorrelationId>
</soap:Header>
~~~

Giá trị ví dụ chỉ để minh họa. Header phải được validate về chiều dài, character set và policy. Không dùng Header này thay thế W3C traceparent; hai loại metadata có vòng đời và semantics khác nhau.

Nếu correlation ID được truyền qua SOAP Header, server cần đọc qua SOAP API/interceptor và lưu vào context. Đừng lấy bằng regex trên raw XML; prefix có thể thay đổi và XML namespace cần được xử lý đúng.

## 5. Thiết lập correlation context trong Spring-WS

### 5.1. Dùng EndpointInterceptor

EndpointInterceptor có thể đọc SOAP Header và gắn correlation metadata vào MessageContext hoặc diagnostic context:

~~~java
public final class CorrelationInterceptor
        implements EndpointInterceptor {
    private static final String CORRELATION_KEY =
        "diagnostic.correlationId";

    @Override
    public boolean handleRequest(
            MessageContext context, Object endpoint) {
        String correlationId =
            readAndValidateCorrelationHeader(context.getRequest());
        if (correlationId == null) {
            correlationId = generateCorrelationId();
        }
        context.setProperty(CORRELATION_KEY, correlationId);
        MDC.put("correlation_id", correlationId);
        return true;
    }

    @Override
    public boolean handleResponse(
            MessageContext context, Object endpoint) {
        return true;
    }

    @Override
    public boolean handleFault(
            MessageContext context, Object endpoint) {
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context, Object endpoint,
            Exception exception) {
        MDC.remove("correlation_id");
    }
}
~~~

Đây là skeleton, không phải implementation hoàn chỉnh để đưa thẳng vào production. Cần xử lý context lồng nhau, exception trong handleRequest, async handoff và thứ tự nhiều interceptor. Nếu một interceptor return false, framework dừng endpoint chain; phải bảo đảm MDC cleanup theo lifecycle của phiên bản Spring-WS đang dùng. Có thể an toàn hơn khi đặt context management trong Servlet filter hoặc dùng try/finally ở component sở hữu lifecycle bao trọn request.

Một lựa chọn khác là Servlet filter tạo correlation ID sớm trước MessageDispatcherServlet, sau đó endpoint interceptor chỉ đọc context. Cách này giúp correlation ID vẫn có mặt trong log khi SOAP parsing hoặc endpoint mapping thất bại trước khi interceptor được gọi.

### 5.2. Servlet filter là điểm tạo context sớm

Ví dụ filter tạo correlation ID nếu request chưa có giá trị hợp lệ:

~~~java
public final class CorrelationIdFilter extends OncePerRequestFilter {
    private static final String HEADER = "X-Correlation-ID";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        String supplied = request.getHeader(HEADER);
        String correlationId = validate(supplied)
            ? supplied
            : UUID.randomUUID().toString();

        response.setHeader(HEADER, correlationId);
        String previous = MDC.get("correlation_id");
        try {
            MDC.put("correlation_id", correlationId);
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove("correlation_id");
            } else {
                MDC.put("correlation_id", previous);
            }
        }
    }

    private boolean validate(String value) {
        return value != null
            && value.length() <= 64
            && value.matches("[A-Za-z0-9._-]+");
    }
}
~~~

Filter chỉ là ví dụ; cần cấu hình thứ tự với Spring Security và các filter khác. Nếu request bị HTTP authentication filter chặn trước filter này, correlation ID có thể chưa được tạo. Đặt filter trước/sau security phải dựa trên mục tiêu: muốn correlation cho cả 401/403 thì đặt ở vị trí sớm phù hợp nhưng vẫn bảo đảm không tin dữ liệu caller và không bypass security.

Không dùng giá trị client gửi làm log key mà chưa validate. Tên header phải được quy định thống nhất giữa gateway, client và service; tránh chấp nhận nhiều header trùng tên có giá trị mâu thuẫn.

## 6. Log có cấu trúc: ghi đủ để điều tra

### 6.1. Log event thay vì nối chuỗi tùy tiện

Log có cấu trúc cho phép truy vấn theo trường và tổng hợp theo operation/outcome:

~~~json
{
  "timestamp": "2026-11-27T08:15:30.125Z",
  "level": "WARN",
  "service.name": "orders-soap",
  "event.name": "soap.endpoint.mapping.failed",
  "correlation_id": "c-7f4e4a9d",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "soap.version": "1.1",
  "soap.payload_qname": "{https://example.com/orders/v1}GetOrderRequest",
  "soap.action": "GetOrder",
  "http.route": "/ws",
  "outcome": "no_endpoint_mapping",
  "duration_ms": 12
}
~~~

Đây là schema minh họa. Trong thực tế, tuân convention telemetry của hệ thống (ví dụ OpenTelemetry semantic conventions) và không tạo nhiều key khác nhau cho cùng ý nghĩa.

### 6.2. Các trường thường hữu ích

| Nhóm | Trường gợi ý |
| --- | --- |
| Service | service name, version, environment, instance |
| Request | correlation ID, trace ID, span ID, method, route |
| SOAP | SOAP version, payload QName, action, attachment count/bytes |
| Mapping | mapping type, endpoint identifier, mapping outcome |
| Security | authentication outcome/category, policy name; không log credential |
| Dependency | dependency name, operation, timeout/retry outcome |
| Result | success/fault/rejection category, HTTP status |
| Timing | queue wait, parse/security/endpoint/dependency duration |
| Integrity | log event ID, evidence source, collection timestamp |

Không phải mọi request đều cần tất cả trường. Chọn schema nhất quán, dùng enum hoặc bounded values cho label và tránh cardinality cao.

### 6.3. Không dùng raw identifier làm metric label

Không đặt correlation ID, trace ID, order ID, customer ID, email hoặc full URL làm Prometheus/Micrometer label. Mỗi giá trị tạo một time series riêng, làm cardinality tăng rất nhanh và có thể rò thông tin.

Correlation ID/trace ID phù hợp trong log hoặc trace attributes với sampling/retention kiểm soát. Metric label nên có giá trị hữu hạn như operation name, outcome, dependency name, fault category và partner tier.

## 7. Thu bằng chứng SOAP mà không lưu raw Envelope

### 7.1. Metadata thường đủ cho bước đầu

Khi một SOAP operation thất bại, phần lớn chẩn đoán ban đầu có thể dựa vào correlation ID và trace ID; HTTP route, method, status và content type; SOAP version; payload root QName; SOAPAction hoặc WS-Addressing Action đã validate; số lượng/kích thước attachment; endpoint mapping result; SOAP Fault code/subcode và error category; processing duration theo từng stage; downstream dependency và outcome.

Không cần ghi toàn bộ Body để trả lời các câu hỏi này.

### 7.2. QName và action có thể được log an toàn hơn payload

Payload QName thường là metadata contract, nhưng vẫn nên giới hạn độ dài và tránh đưa giá trị tùy ý do caller điều khiển vào log. Action URI cũng nên normalize theo danh sách operation được công bố hoặc truncate/bucket khi không nhận diện được.

Nếu cần log unknown QName, ghi một dạng bounded/escaped representation và giữ correlation ID để tra cứu event liên quan. Không log toàn XML chỉ vì QName không nhận diện được.

### 7.3. SOAP Fault evidence

Có thể ghi fault code (Sender/Receiver hoặc Client/Server theo SOAP version); subcode nếu contract cho phép; error category nội bộ đã được ánh xạ; mapping/resolver stage; correlation ID; có/không có Detail hoặc QName của detail root nếu an toàn.

Tránh log full Fault Detail theo mặc định. Fault detail đôi khi chứa SQL text, hostname, class name, stack trace, filesystem path hoặc dữ liệu do dependency trả về.

### 7.4. Attachment evidence

Với MTOM/MIME, ghi số part, content type đã allowlist, kích thước bucket và scan outcome; không dump bytes, Base64 hoặc filename có thể chứa thông tin cá nhân; nếu phải giữ attachment làm bằng chứng, đặt nó trong evidence vault có encryption/access control/retention riêng, không đẩy vào application log; ghi checksum của evidence file khi có quy trình bảo toàn phù hợp.

## 8. Redaction và data minimization

### 8.1. Phân loại dữ liệu trước khi log

| Dữ liệu | Xử lý khuyến nghị |
| --- | --- |
| Password, UsernameToken password/digest, nonce | Không log; redact tuyệt đối |
| Authorization header, bearer token, cookie | Không log; redact tuyệt đối |
| Private key, secret, keystore password | Không log; không đưa vào trace |
| XML SignatureValue, encrypted key material | Không log raw |
| Certificate private material | Không log |
| Certificate fingerprint/serial | Chỉ log khi có nhu cầu vận hành, đánh giá privacy và giới hạn retention |
| SOAP Body/PII/financial values | Không log mặc định; dùng allowlisted derived fields |
| Attachment | Không log bytes/base64; chỉ metadata tối thiểu |
| Correlation ID/trace ID | Có thể log; không chứa business data |
| Fault code/outcome/duration | Thường an toàn hơn, vẫn kiểm soát cardinality |

### 8.2. Redact trước khi log

Redaction phải diễn ra **trước sink**, không phải sau khi log đã được gửi tới ELK/SIEM. Nếu appender nhận raw message rồi downstream pipeline mới redact, dữ liệu bí mật đã rời process.

Ưu tiên không serialize secrets vào log event ngay từ đầu; dùng allowlist field để tạo diagnostic record; nếu phải xử lý XML, dùng namespace-aware parser và remove/mask trường cụ thể; không dùng regex replace raw XML như cơ chế bảo mật duy nhất; kiểm thử output sau mọi appender/encoder.

Regex trên XML dễ sai vì prefix thay đổi, namespace có thể dùng default, element có thể lồng nhau và text có thể được escape/CDATA. Redaction không đúng có thể bỏ sót token hoặc che nhầm field khác.

### 8.3. Ví dụ: tạo safe diagnostic summary

Không log raw request:

~~~java
log.info("Received SOAP request: {}", rawEnvelope);
~~~

Hãy tạo summary đã allowlist:

~~~java
log.info(
    "SOAP request received operation={} soapVersion={} "
        + "payloadBytes={} attachmentCount={} correlationId={}",
    operationName,
    soapVersion,
    payloadSize,
    attachmentCount,
    correlationId
);
~~~

operationName phải được lấy/giới hạn theo QName đã parse; payloadSize và attachmentCount là số liệu; correlation ID đã validate. Trong code thực, dùng structured arguments/JSON encoder thay vì nối message chuỗi; các trường được xuất riêng để truy vấn.

Không log payload orderId, customer name, authentication token hoặc raw SOAP message trong event này. Correlation ID cho phép tìm event liên quan mà không sao chép dữ liệu nghiệp vụ vào dòng log.

### 8.4. Không băm token rồi coi là đã an toàn

Hash một token hoặc identifier vẫn có thể tạo giá trị liên kết lâu dài, cho phép correlation ngoài ý muốn hoặc tấn công dictionary với giá trị ít entropy. Đừng thay raw secret bằng hash trong log trừ khi có threat model, keyed HMAC, key rotation và mục đích vận hành được phê duyệt.

Với credential, tốt nhất không log bất kỳ biến thể nào. Với business ID cần đối chiếu, cân nhắc tokenization hoặc keyed pseudonym được quản lý riêng, thay vì hash trực tiếp.

## 9. MDC và structured logging trong Spring

### 9.1. MDC hữu ích ở đâu?

SLF4J MDC cho phép log encoder tự thêm context như correlation ID và tenant tier:

~~~java
MDC.put("correlation_id", correlationId);
MDC.put("soap_operation", operation);
try {
    log.info("SOAP request accepted");
    process(request);
} finally {
    MDC.remove("correlation_id");
    MDC.remove("soap_operation");
}
~~~

Không đặt raw SOAP Header, Authorization, UsernameToken hoặc Body vào MDC. MDC thường được xuất ra mọi log event trong scope, vì vậy một field nhạy cảm sẽ bị nhân bản ở mọi log.

### 9.2. Async boundary

Khi submit công việc vào executor:

~~~java
String correlationId = MDC.get("correlation_id");
executor.execute(() -> {
    try {
        if (correlationId != null) {
            MDC.put("correlation_id", correlationId);
        }
        processAsync();
    } finally {
        MDC.remove("correlation_id");
    }
});
~~~

Đây là cách tối giản chỉ truyền một key. Trong hệ thống thực, có thể dùng TaskDecorator, Micrometer Context Propagation hoặc OpenTelemetry Context storage. Chỉ capture keys/contexts cần thiết, và luôn restore/clear để ngăn leak sang task kế tiếp.

### 9.3. Không dựa vào MDC để truyền security principal

MDC chỉ dành cho chẩn đoán. Không dùng MDC user field để authorize hoặc quyết định tenant. SecurityContext phải được truyền bằng cơ chế security framework hỗ trợ và có lifecycle riêng.

## 10. Distributed tracing với OpenTelemetry

### 10.1. Span theo ranh giới có ý nghĩa

Một trace SOAP có thể có HTTP server span tại gateway/servlet; SOAP dispatch span; security validation span; endpoint/application span; DB client span; outbound SOAP/HTTP client span; async producer/consumer span nếu có context propagation.

Không tạo span cho mọi dòng code. Span nên thể hiện ranh giới có thể hành động: mapping, security validation, database call, downstream operation, attachment scanning.

### 10.2. Attributes nên có giới hạn

Attributes có thể gồm operation QName, SOAP version, endpoint mapping type, partner tier, fault category, retry attempt và dependency name. Tránh body text, username, email, order ID, certificate content hoặc token.

Không đưa dynamic high-cardinality business ID vào span name. Span name nên ổn định, ví dụ SOAP GetOrder thay vì SOAP GetOrder ORD-1001.

### 10.3. Sampling và evidence gaps

Sampling nghĩa là không phải mọi request đều có trace được lưu. Do đó correlation ID và structured logs vẫn cần tồn tại theo retention policy; metrics tổng hợp vẫn cần đầy đủ; error sampling có thể tăng xác suất lưu trace lỗi nhưng phải kiểm soát chi phí/PII; không coi không tìm thấy trace là bằng chứng request không xảy ra.

Tail sampling ở collector có thể giữ trace có error/latency cao, nhưng collector phải có capacity và memory giới hạn. Trace exporter outage không được làm SOAP request thất bại; dùng batch/export queue bounded và retry/drop policy có kiểm soát.

## 11. Thu bằng chứng an toàn theo từng lớp

### 11.1. HTTP/gateway evidence

Thu timestamp UTC; correlation/request ID; route name (không nhất thiết full URL); HTTP method, status, content type; request/response byte count; client network identity theo privacy policy; upstream timing, retry count, proxy route.

Không mặc định lưu full query string, cookies, authorization header hoặc request body.

### 11.2. Spring-WS evidence

Thu SOAP version; payload QName; SOAPAction/WS-Addressing Action đã giới hạn; mapping type/result; endpoint identifier ổn định; interceptor decision category; Fault code/subcode; parse/mapping/endpoint duration.

### 11.3. Application/database evidence

Thu business operation name; safe resource reference/pseudonymous key nếu cần; transaction outcome; DB operation duration và affected row count; outbox/event record ID; idempotency outcome. Không log full SQL parameter values hoặc PII.

### 11.4. Downstream evidence

Thu dependency service name; operation; correlation/trace context; connect/read duration; HTTP status hoặc SOAP Fault category; retry attempt, circuit state, timeout/rejection. Không copy downstream response body vào log mặc định.

## 12. Bảo toàn evidence bundle cho incident

### 12.1. Evidence bundle nên gồm gì?

Một bundle đủ để điều tra có thể chứa:

1. Incident ID và incident timeline;
2. Correlation ID, trace ID hoặc danh sách request IDs liên quan;
3. Các structured log event đã redact;
4. Trace/span export nếu có;
5. HTTP status/header allowlist và timing;
6. SOAP metadata summary (QName, action, version, fault category);
7. Metrics snapshot trước/trong/sau incident;
8. Dependency status/change events;
9. Deployment/config version và release identifier;
10. Người thu thập, thời điểm, nguồn và checksum của bundle.

Không đưa raw production SOAP Envelope hoặc secrets vào bundle theo mặc định. Nếu payload mẫu là bắt buộc cho forensic, cần phê duyệt, redaction có kiểm chứng, encryption, access logging, retention ngắn và kho evidence tách khỏi log search thông thường.

### 12.2. Integrity và chain of custody

Đối với incident quan trọng:

- Giữ file gốc từ nguồn có thẩm quyền khi được phép thu thập;
- Tạo bản làm việc đã redact riêng;
- Ghi hash cryptographic (ví dụ SHA-256) của artifact đã lưu;
- Ghi thời gian UTC, source system, collector và tool/version;
- Ghi mọi thao tác chuyển đổi/redaction;
- Lưu ở vị trí access-controlled, encryption at rest/in transit;
- Ghi access/audit log;
- Chốt retention/disposal theo policy.

Hash chứng minh file không đổi so với bản đã hash; nó không chứng minh nội dung ban đầu đúng hoặc nguồn gửi là thật. Chain of custody cần source provenance, access controls và collection procedure, không chỉ checksum.

### 12.3. Clock synchronization

Các máy chủ cần đồng bộ thời gian bằng NTP/time service được quản trị. Ghi timestamp UTC và timezone/clock metadata khi cần. Trace timestamps từ nhiều host có thể khó sắp xếp nếu clock skew lớn; span parent-child giúp hiểu quan hệ nhưng không xóa hoàn toàn vấn đề clock.

Không dùng timestamp của client chưa xác thực làm thời điểm sự kiện server. Ghi rõ event time do server quan sát và client timestamp nếu contract có, với nguồn khác nhau.

## 13. Incident workflow: từ symptom tới kết luận

### 13.1. Bước 1 — Ghi nhận triệu chứng

Ghi thời điểm bắt đầu/kết thúc, operation ảnh hưởng, partner scope, error rate, latency percentiles và impact người dùng. Không kết luận nguyên nhân từ một log sample.

### 13.2. Bước 2 — Tạo incident ID

Tạo incident ID độc lập với correlation ID. Incident có thể bao gồm hàng nghìn requests/correlations. Từ incident ID, duy trì danh sách correlation IDs/traces liên quan trong evidence index có access control.

### 13.3. Bước 3 — Chọn mẫu request đại diện

Chọn một số request thành công và thất bại cùng operation/version/partner class trong khoảng thời gian gần nhau. Dùng correlation ID để tìm log/trace; nếu trace missing do sampling, dùng logs và metrics.

### 13.4. Bước 4 — Dựng timeline

| UTC | Nguồn | Sự kiện | Bằng chứng |
| --- | --- | --- | --- |
| 08:15:30.100 | Gateway | Nhận POST /ws | Request ID, 2.1 KB |
| 08:15:30.105 | SOAP server | Parse envelope | SOAP 1.1, QName GetOrderRequest |
| 08:15:30.108 | Endpoint mapping | Mapping thành công | Endpoint GetOrder |
| 08:15:30.112 | Inventory client | Read timeout | 800 ms |
| 08:15:31.001 | Application | Trả dependency Fault | Category TEMPORARY_UNAVAILABLE |
| 08:15:31.006 | Gateway | HTTP response | Status theo SOAP binding |

Timestamp và số liệu chỉ minh họa. Timeline thật phải dựa trên event timestamps và trace relationships, không tự suy ra thứ tự chỉ từ log ingestion time.

### 13.5. Bước 5 — Phân biệt facts, hypotheses và unknowns

Ví dụ:

- **Fact:** log ghi inventory.timeout trong span con của SOAP request.
- **Hypothesis:** inventory service chậm làm request vượt deadline.
- **Unknown:** inventory timeout bắt đầu trước hay sau DB lock wait.

Tiếp tục thu DB pool/wait metrics hoặc traces khác để xác minh. Không biến hypothesis thành root cause trong báo cáo trước khi có bằng chứng.

### 13.6. Bước 6 — Ghi lại remediation và verification

Sau thay đổi, ghi deployment version/config diff, thời gian, request samples đã redact, metric trước/sau và kết quả regression test. Giữ correlation IDs của các request tái hiện lỗi để so sánh.

## 14. Ví dụ: một structured diagnostic event an toàn

~~~java
public void logMappingFailure(
        String correlationId,
        String soapVersion,
        QName payloadName,
        String mappingType,
        long durationMs) {
    log.warn(
        "SOAP endpoint mapping failed correlationId={} "
            + "soapVersion={} payloadNamespace={} "
            + "payloadLocalPart={} mappingType={} durationMs={}",
        correlationId,
        soapVersion,
        safeNamespace(payloadName.getNamespaceURI()),
        safeLocalPart(payloadName.getLocalPart()),
        mappingType,
        durationMs
    );
}
~~~

safeNamespace và safeLocalPart cần giới hạn độ dài, ký tự và không cho CR/LF/control characters làm log injection. Trong code thực, dùng structured arguments/JSON encoder thay vì nối message chuỗi; các trường được xuất riêng để truy vấn.

Không log payload orderId, customer name, authentication token hoặc raw SOAP message trong event này. Correlation ID cho phép tìm những event liên quan mà không sao chép dữ liệu nghiệp vụ vào dòng log.

## 15. Kiểm thử correlation và redaction

Observability cần có test giống security feature. Những lỗi thường gặp là correlation ID bị mất ở async boundary, MDC rò sang request sau, logger ghi raw SOAP Body qua một appender khác hoặc exception message chứa token.

### 15.1. Correlation propagation test

Kiểm tra:

- Request không có correlation ID được server tạo ID;
- Request có ID hợp lệ được giữ hoặc ánh xạ theo policy;
- ID quá dài/ký tự điều khiển bị từ chối hoặc thay mới;
- Response trả ID theo contract/header policy;
- Downstream call nhận cùng trace context;
- Async consumer khôi phục correlation metadata;
- Thread được dọn context sau request.

### 15.2. MDC cleanup test

Giả lập hai request chạy liên tiếp trên cùng worker thread:

1. Request A dùng ID A;
2. Request A hoàn thành dù endpoint ném exception;
3. Request B không có ID đầu vào;
4. Log của B phải dùng ID B, không phải A.

Thêm test khi async task ném exception để chắc chắn finally luôn clear/restore context.

### 15.3. Redaction canary test

Tạo test secret giả có chuỗi dễ nhận diện:

~~~text
CANARY-SECRET-DO-NOT-LOG-9d4b
~~~

Đặt chuỗi này lần lượt trong HTTP Authorization header; SOAP UsernameToken password; SOAP Body field nhạy cảm; SOAP Fault Detail; Exception message; Attachment filename/metadata.

Gửi request qua toàn bộ logging pipeline trong test và assert chuỗi canary **không xuất hiện** trong log events, MDC, trace attributes, exception telemetry, metrics labels hoặc exported diagnostic bundle.

Không dùng secret production để kiểm thử redaction. Test cần xem cả appender/encoder và exporter, không chỉ assert một logger call.

### 15.4. Structured log schema test

Kiểm tra event có các field cần thiết; field type đúng; enum/bounded value hợp lệ; không có PII/secrets; timestamp UTC parse được; correlation ID không chứa CR/LF; trace/span ID đúng format khi hiện diện.

## 16. Quy trình khi phát hiện secrets đã lọt vào log

Nếu token/password/private key hoặc payload nhạy cảm xuất hiện trong log:

1. Xác định log sink, index, bucket, replica, archive và export destinations bị ảnh hưởng.
2. Hạn chế truy cập ngay theo incident procedure; không tiếp tục gửi link/screenshot chứa secret.
3. Xác định loại secret, thời gian lộ và phạm vi truy cập.
4. Rotate/revoke credential, key, token hoặc certificate theo mức độ ảnh hưởng.
5. Tạm ngừng logger/appender/payload tracing gây rò rỉ sau khi đánh giá impact.
6. Xóa/expire bản sao theo retention/legal hold policy; không tự xóa evidence phải bảo toàn cho điều tra.
7. Ghi nhận ai đã truy cập, export hoặc tải artifact.
8. Thêm canary regression test và kiểm tra mọi sink khác.

Không chỉ redact bản hiển thị ở dashboard. Dữ liệu có thể còn trong index gốc, replica, backup, object storage, message queue hoặc vendor support bundle.

## 17. Những sai lầm thường gặp

| Sai lầm | Rủi ro | Cách sửa |
| --- | --- | --- |
| Log toàn bộ SOAP Envelope | Lộ PII, token, signature và business data | Log allowlisted metadata |
| Dùng order ID làm correlation ID | Lộ/định danh nghiệp vụ và dễ đoán | Tạo opaque random ID riêng |
| Dùng trace ID làm authorization token | Tin dữ liệu caller-controlled | SecurityContext riêng |
| Không clear MDC | Request sau mang context của request trước | try/finally và async context wrapper |
| Regex mask password trong XML | Bỏ sót namespace/prefix/CDATA variants | Không log raw XML; parser-aware allowlist |
| Redact ở SIEM sau ingest | Secret đã rời application | Redact trước logging sink |
| Ghi toàn bộ exception stack vào SOAP Fault | Lộ internals tới consumer | Public fault mapping an toàn |
| Hash token rồi log | Vẫn có thể liên kết/dictionary attack | Không log token |
| Dùng trace ID làm metric label | Cardinality bùng nổ | Trace IDs trong logs/traces |
| Không có trace do sampling nên kết luận không request | Evidence gap bị hiểu sai | Kết hợp logs/metrics/gateway access record |
| Dùng ingestion time làm event order | Pipeline delay gây timeline sai | Event timestamp + span relationship |
| Evidence bundle không có provenance | Khó kiểm chứng nguồn | Source, collector, timestamp, hash, audit |

## 18. Checklist thu bằng chứng an toàn

### Correlation

- [ ] Correlation ID opaque, bounded và validate.
- [ ] Trace context được extract/inject bằng propagator chuẩn.
- [ ] Message ID, idempotency key và business ID có semantics riêng.
- [ ] Correlation context xuyên HTTP, SOAP, downstream và async boundary.
- [ ] MDC/ThreadLocal được restore/clear trong mọi path.

### Logging và tracing

- [ ] Structured logs có operation, outcome, correlation và stage timing.
- [ ] Payload QName/action được giới hạn và validate.
- [ ] Không log SOAP Envelope, credentials, token, signature hoặc attachment bytes mặc định.
- [ ] Không đưa dynamic IDs thành metric labels/span names.
- [ ] Export queue/sampling có capacity và failure policy hữu hạn.

### Redaction và access

- [ ] Allowlist fields trước log sink.
- [ ] Redaction được test bằng canary secrets qua mọi appender/exporter.
- [ ] Log/evidence stores có encryption, role-based access và audit log.
- [ ] Retention/deletion phù hợp data policy.
- [ ] Diagnostic export không chứa raw secrets hoặc PII không cần thiết.

### Incident evidence

- [ ] Incident ID tách biệt correlation ID.
- [ ] Bundle ghi source, UTC timestamp, collector và version.
- [ ] Có bản gốc/bản redact tách biệt khi policy yêu cầu.
- [ ] Integrity checksum và access chain được ghi nhận.
- [ ] Facts, hypotheses và unknowns được phân biệt.
- [ ] Remediation có deployment/config version và verification result.

## 19. Câu hỏi tự kiểm tra

1. Correlation ID khác trace ID ở mục đích nào?
2. Span ID biểu diễn điều gì trong distributed trace?
3. SOAP MessageID và WS-Addressing RelatesTo có thay thế correlation ID không?
4. Vì sao correlation ID không phải credential?
5. Khi nào server nên tạo correlation ID mới thay vì giữ giá trị client gửi?
6. Trace context được truyền qua HTTP SOAP transport thế nào?
7. Vì sao SOAP Header correlation ID không thay thế W3C traceparent?
8. MDC có thể gây rò context thế nào khi thread được tái sử dụng?
9. Vì sao async executor cần context propagation/cleanup?
10. Những trường nào đủ để chẩn đoán mapping failure mà không log payload?
11. Vì sao raw SOAP Fault Detail cũng có thể chứa secrets?
12. Vì sao redaction phải xảy ra trước khi event tới log sink?
13. Regex masking XML có những giới hạn nào?
14. Hash token có bảo đảm không thể liên kết hoặc suy ra không?
15. Vì sao không nên dùng trace ID/correlation ID làm Prometheus label?
16. Evidence bundle cần source provenance và integrity metadata nào?
17. Hash file chứng minh được gì và không chứng minh được gì?
18. Vì sao ingestion timestamp có thể gây timeline sai?
19. Làm thế nào phát hiện log đã chứa secrets bằng canary tests?
20. Cần làm gì khi phát hiện token production đã xuất hiện trong log archive?

## 20. Bài tập thực hành

**Bối cảnh:** Một SOAP service SubmitOrder gọi inventory, payment và publish event. Partner phản ánh một số request timeout sau khi đã gửi; đội support cần trace luồng xử lý nhưng security review cấm ghi raw SOAP Body, UsernameToken hoặc attachment vào logs.

### Phần A — Thiết kế ID

1. Chọn format correlation ID opaque; validate inbound X-Correlation-ID.
2. Định nghĩa trace context theo W3C Trace Context.
3. Quy định SOAP Header CorrelationId có cần trong contract hay chỉ dùng HTTP metadata.
4. Phân biệt SOAP MessageID, idempotency key và business order ID.

### Phần B — Propagation

5. Implement servlet filter tạo/validate correlation ID.
6. Thêm endpoint interceptor để ghi QName/action và liên kết MessageContext.
7. Instrument outbound inventory/payment clients.
8. Propagate context qua outbox event và consumer.
9. Kiểm tra MDC cleanup khi request success, Fault và exception.

### Phần C — Safe diagnostics

10. Định nghĩa JSON log schema cho request received, mapping, security outcome, dependency call và response.
11. Chỉ log payload QName, sizes, fault category và operation; không log raw Body/Header secrets.
12. Thêm redaction/allowlist trước appender/exporter.
13. Tạo canary secrets trong Authorization, UsernameToken, Body, Fault Detail và attachment metadata.
14. Assert canary không xuất hiện trong logs, traces, metrics labels và diagnostic bundle.

### Phần D — Evidence và incident

15. Tạo evidence bundle mẫu có incident ID, correlation IDs, trace IDs, logs đã redact, metrics và deployment version.
16. Ghi source/UTC timestamp/collector/hash/access metadata.
17. Dựng timeline cho request timeout và phân loại facts/hypotheses/unknowns.
18. Mô phỏng token bị log nhầm; viết quy trình containment, rotation, archive review và regression prevention.

**Tiêu chí đạt:** support nối được gateway, Spring-WS, downstream và async event bằng correlation/trace context; xác định được stage/time/fault category; không có canary secret trong bất kỳ diagnostic output nào; evidence bundle có provenance và integrity; context không rò sang request tiếp theo.

## 21. Tài liệu tham khảo chính thức

- [W3C Trace Context](https://www.w3.org/TR/trace-context/): định dạng và propagation của traceparent/tracestate.
- [W3C Baggage](https://www.w3.org/TR/baggage/): propagation metadata và các giới hạn cần cân nhắc.
- [OpenTelemetry Specification — Context](https://opentelemetry.io/docs/specs/otel/context/): context propagation và execution context.
- [OpenTelemetry Java](https://opentelemetry.io/docs/languages/java/): instrumentation, SDK, propagation và tracing cho Java.
- [SLF4J Manual — MDC](https://www.slf4j.org/manual.html#mdc): mapped diagnostic context.
- [Spring Framework — Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html): Micrometer Observation và context propagation trong Spring.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu nên/không nên ghi log, protection và event handling.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): bảo vệ, luân chuyển và quản trị secrets.
- [Spring Web Services Reference 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): MessageContext, EndpointInterceptor, WebServiceTemplate và endpoint processing.

API/instrumentation cụ thể phụ thuộc Spring, SLF4J, Micrometer, OpenTelemetry agent và HTTP sender version của dự án. Đối chiếu dependency thực tế, kiểm thử propagation và redaction trên toàn bộ log/export pipeline trước khi bật ở production.

## 22. Tổng kết

**Định danh tương quan giúp nối sự kiện; distributed trace giải thích quan hệ và thời gian giữa các bước; structured logs cung cấp bằng chứng vận hành; evidence bundle bảo toàn nguồn gốc và integrity.** Các cơ chế này chỉ hữu ích khi context được truyền nhất quán, được dọn đúng lifecycle và không chứa secrets.

Với Spring-WS, hãy bắt đầu correlation ở ranh giới HTTP đủ sớm để bao phủ cả lỗi parse/mapping, dùng endpoint interceptor để bổ sung SOAP metadata, propagator chuẩn cho outbound HTTP calls và cơ chế context propagation cho async work. Ghi QName, action, fault category, timing và sizes thay cho raw Envelope. Redact trước log sink, kiểm thử bằng canary secrets và giới hạn quyền/retention của evidence store.

**Ghi nhớ:** có thể điều tra một SOAP request bằng correlation ID, trace/span, QName, action, stage outcome và timing mà không cần lưu password, token hay toàn bộ payload. Bằng chứng tốt là bằng chứng đủ dùng, có nguồn gốc và được bảo vệ.
