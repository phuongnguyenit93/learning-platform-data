# Metadata xác thực, truy vết và thông tin ngữ cảnh

Trong một ứng dụng RSocket, payload mang dữ liệu của thao tác, còn metadata mang thông tin mô tả cách thao tác đó cần được xử lý. Metadata có thể cho biết ai đang gọi, request thuộc tenant nào, cần áp dụng chính sách bảo mật nào hoặc phải nối vào trace nào. Nhờ vậy, cùng một payload nghiệp vụ có thể đi qua nhiều lớp hạ tầng mà không phải nhồi các thông tin vận hành vào cấu trúc dữ liệu của domain.

Metadata chỉ hữu ích khi hai phía thống nhất cách mã hóa, MIME type và ý nghĩa của từng trường. Một chuỗi mang tên người dùng không tự trở thành bằng chứng xác thực; một trace ID không tự tạo ra distributed tracing; và một tenant ID do client gửi không tự chứng minh client được quyền truy cập tenant đó. Bài này trình bày cách thiết kế metadata cho xác thực, truy vết và ngữ cảnh trong RSocket, với ví dụ Java và Spring Boot.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt data và metadata trong một RSocket payload, cũng như metadata lúc thiết lập kết nối và metadata theo từng request.
- Giải thích vai trò của MIME type và composite metadata.
- Truyền thông tin xác thực và dùng danh tính đã được server xác minh để phân quyền.
- Mang trace context và correlation ID qua các request-response, request-stream và request-channel.
- Chọn thông tin ngữ cảnh phù hợp để đặt trong metadata, đồng thời giới hạn kích thước và bảo vệ dữ liệu.
- Tổ chức metadata extractor và handler trong Spring RSocket.

## 1. Data và metadata trong RSocket

Một RSocket payload có hai phần độc lập:

- **Data** chứa nội dung nghiệp vụ mà handler cần xử lý, ví dụ lệnh tạo đơn hàng, truy vấn giá hoặc một bản ghi cảm biến.
- **Metadata** chứa thông tin đi kèm để định tuyến, xác thực, truy vết hoặc áp dụng ngữ cảnh xử lý.

Ví dụ, khi tìm đơn hàng, data có thể chỉ chứa mã đơn:

~~~json
{
  "orderId": "ORD-1042"
}
~~~

Metadata của cùng request có thể chứa route, thông tin tenant và trace context. Nhờ vậy, cấu trúc OrderQuery không cần chứa token truy cập, trace ID hay locale chỉ để phục vụ hạ tầng.

Metadata không thay thế data. Nếu một giá trị là một phần của nghiệp vụ, cần được lưu, kiểm tra hoặc hiển thị như dữ liệu domain, hãy đặt nó trong data. Nếu giá trị chỉ hướng dẫn cách request được xác thực, theo dõi hoặc xử lý ở nhiều tầng, metadata thường phù hợp hơn.

### 1.1. Metadata ở cấp kết nối và cấp request

RSocket có thể mang metadata trong hai phạm vi:

| Phạm vi | Thời điểm truyền | Ví dụ | Vòng đời |
|---|---|---|---|
| Setup metadata | Khi client thiết lập RSocket connection | Thông tin xác thực ban đầu, khả năng hoặc ngữ cảnh kết nối | Gắn với kết nối cho đến khi kết nối kết thúc |
| Request metadata | Trong payload của một interaction | Route, trace context, tenant context, request ID | Gắn với request hoặc message mang metadata đó |

Setup metadata hữu ích khi một kết nối đại diện cho một client hoặc một phiên đã xác thực. Request metadata phù hợp với dữ liệu thay đổi theo từng thao tác, chẳng hạn trace context, deadline hoặc khóa idempotency.

Một kết nối RSocket có thể tồn tại lâu hơn một request. Vì vậy, không nên giả định mọi thông tin ở setup đều còn đúng trong toàn bộ vòng đời kết nối. Token có thể hết hạn hoặc bị thu hồi, người dùng có thể đổi tenant đang thao tác, và mỗi request có thể thuộc một trace khác nhau. Hệ thống cần xác định rõ thông tin nào là thuộc tính của kết nối và thông tin nào phải được kiểm tra lại ở từng request.

### 1.2. MIME type mô tả metadata

RSocket sử dụng MIME type để cho bên nhận biết cách diễn giải metadata. Một số MIME type được dùng phổ biến:

| MIME type | Mục đích |
|---|---|
| **message/x.rsocket.composite-metadata.v0** | Đóng gói nhiều metadata entry trong một metadata section |
| **message/x.rsocket.routing.v0** | Thông tin route để chọn handler |
| **message/x.rsocket.authentication.v0** | Nhóm metadata xác thực |
| **message/x.rsocket.authentication.simple.v0** | Thông tin xác thực dạng username/password |
| **message/x.rsocket.authentication.bearer.v0** | Bearer token |
| **message/x.rsocket.tracing-zipkin.v0** | Metadata tracing theo định dạng Zipkin của RSocket |

Tên MIME type và định dạng nội dung phải khớp với thư viện hoặc extension mà hai phía sử dụng. Không nên tự tạo một MIME type trùng với loại đã được chuẩn hóa.

Nếu cần mang nhiều loại metadata trong cùng một payload, client và server thường chọn composite metadata làm metadata MIME type của kết nối. Mỗi entry bên trong composite metadata lại có MIME type riêng để xác định cách giải mã. Ví dụ, một payload có thể chứa routing metadata, authentication metadata và metadata ngữ cảnh do ứng dụng định nghĩa.

Composite metadata là một định dạng nhị phân có cấu trúc, không phải một chuỗi JSON tùy ý. Hãy dùng codec hoặc API metadata của RSocket/Spring để tạo và đọc entry; tránh tự nối chuỗi hoặc tự cắt byte theo giả định riêng.

## 2. Metadata xác thực và danh tính

Xác thực trả lời câu hỏi **ai đang gọi**. Phân quyền trả lời câu hỏi **người gọi đó được phép làm gì**. Hai bước có liên quan nhưng không thể thay thế cho nhau.

### 2.1. Truyền thông tin xác thực

Client có thể gửi thông tin xác thực bằng metadata theo định dạng mà server hỗ trợ. Với bearer token, RSocket định nghĩa MIME type:

~~~text
message/x.rsocket.authentication.bearer.v0
~~~

Token có thể được gửi trong setup metadata để xác thực kết nối hoặc trong request metadata nếu cơ chế bảo mật và vòng đời token yêu cầu xác thực theo từng thao tác. Server phải xác minh chữ ký hoặc tra cứu token theo cơ chế đã chọn, kiểm tra thời hạn, issuer, audience và các điều kiện liên quan trước khi tạo danh tính đã xác thực.

Ví dụ dùng Spring RSocket requester với bearer metadata ở thời điểm kết nối:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeType;
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;

MimeType compositeMimeType =
        MimeType.valueOf("message/x.rsocket.composite-metadata.v0");

RSocketRequester requester = RSocketRequester.builder()
        .metadataMimeType(compositeMimeType)
        .setupMetadata(
                new BearerTokenMetadata(accessToken),
                BearerTokenMetadata.BEARER_AUTHENTICATION_MIME_TYPE
        )
        .connectTcp("localhost", 7000)
        .block();
~~~

Ví dụ này minh họa cách gửi token trong setup metadata. Ứng dụng cần cấu hình Spring Security RSocket ở phía server và cung cấp cơ chế xác minh token phù hợp. Nếu token được làm mới trong khi connection vẫn mở, hãy xác định cách cập nhật danh tính hoặc thiết lập lại kết nối; không mặc định rằng token mới trong bộ nhớ client sẽ tự thay thế token đã gửi ở setup.

Nếu xác thực theo từng request, có thể đính kèm metadata trong request:

~~~java
MimeType bearerMimeType =
        BearerTokenMetadata.BEARER_AUTHENTICATION_MIME_TYPE;

Mono<Order> result = requester.route("orders.find")
        .metadata(
                new BearerTokenMetadata(accessToken),
                bearerMimeType
        )
        .data(new OrderQuery("ORD-1042"))
        .retrieveMono(Order.class);
~~~

Việc có được phép gửi bearer metadata theo từng request hay không phụ thuộc vào security interceptor và cấu hình của server. Chỉ chọn một mô hình rõ ràng: xác thực gắn với connection, xác thực từng request, hoặc kết hợp cả hai với quy tắc ưu tiên và thời hạn cụ thể.

### 2.2. Xác minh và phân quyền ở phía server

Server không được coi dữ liệu do client tự khai là danh tính đã xác minh. Ví dụ, các trường **userId**, **role** hoặc **isAdmin** trong metadata tùy chỉnh không thể được dùng trực tiếp để cấp quyền. Kẻ gọi có thể sửa chúng trước khi gửi request.

Với Spring Security RSocket, cấu hình security interceptor để xác thực metadata và áp dụng quy tắc cho route:

~~~java
import org.springframework.security.config.Customizer;

@Bean
PayloadSocketAcceptorInterceptor rsocketSecurity(
        RSocketSecurity security) {

    security
        .authorizePayload(authorize -> authorize
            .route("orders.*").authenticated()
            .anyRequest().authenticated()
        )
        .jwt(Customizer.withDefaults());

    return security.build();
}
~~~

Ví dụ trên chọn JWT và giả định ứng dụng đã cấu hình reactive JWT decoder. Nếu dùng username/password hoặc authentication manager riêng, thay phần cấu hình JWT bằng cơ chế xác thực tương ứng. Chỉ thêm quy tắc authorization là chưa đủ nếu chưa có thành phần xác minh credential và tạo Authentication.

Sau khi security layer xác thực thành công, handler có thể nhận Principal:

~~~java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.find")
    public Mono<Order> find(
            @Payload OrderQuery query,
            Principal principal) {

        return orderService.findVisibleTo(
                principal.getName(),
                query.orderId()
        );
    }
}
~~~

Service dùng danh tính do security layer cung cấp để kiểm tra quyền truy cập đơn hàng. Không lấy **userId** từ metadata tự khai để thay thế **principal.getName()**.

### 2.3. Tenant context không phải bằng chứng phân quyền

Một request có thể cần tenant ID để chọn schema, database hoặc phạm vi dữ liệu. Client có thể gửi tenant đang muốn thao tác, nhưng server phải xác minh người dùng đã đăng nhập có quyền truy cập tenant đó.

Luồng kiểm tra nên có dạng:

1. Xác thực credential và tạo Principal.
2. Đọc tenant context từ metadata của request.
3. Kiểm tra Principal có quyền sử dụng tenant đó.
4. Tạo context nội bộ đã được xác minh để gọi service hoặc repository.
5. Áp dụng điều kiện tenant ở mọi truy vấn dữ liệu cần thiết.

Không dùng tenant metadata làm điều kiện duy nhất để giới hạn truy vấn. Nếu bỏ qua bước liên kết tenant với Principal, client có thể sửa tenant ID để đọc dữ liệu của tenant khác.

## 3. Metadata truy vết request

Một request realtime có thể đi qua client, gateway, RSocket server, service và database. Khi xảy ra lỗi hoặc độ trễ tăng, đội vận hành cần nối các log và span thuộc cùng một hành trình. Distributed tracing giải quyết vấn đề này bằng cách truyền trace context qua các ranh giới dịch vụ.

### 3.1. Trace ID, span ID và correlation ID

- **Trace ID** định danh toàn bộ hành trình của một thao tác phân tán.
- **Span ID** định danh một đoạn công việc trong trace, ví dụ xử lý một request tại RSocket server.
- **Parent span ID** liên kết span hiện tại với công việc đã gọi nó.
- **Correlation ID** là mã ứng dụng dùng để tìm các log hoặc sự kiện liên quan. Nó có thể trùng với một mã request nhưng không thay thế mô hình trace/span.

Một trace thường có nhiều span:

~~~mermaid
flowchart LR
    A["Client span"] --> B["RSocket server span"]
    B --> C["Order service span"]
    C --> D["Database span"]
~~~

Mỗi service tạo span của riêng mình và truyền context sang service kế tiếp. Không tạo một trace ID mới ở mỗi hop nếu đó vẫn là cùng một thao tác nghiệp vụ.

### 3.2. Truyền trace context qua metadata

RSocket có extension tracing Zipkin với MIME type **message/x.rsocket.tracing-zipkin.v0**. Nếu toàn bộ stack hỗ trợ extension này, hãy dùng định dạng tương ứng thay vì tự diễn giải byte metadata.

Một lựa chọn khác là truyền W3C Trace Context (**traceparent**, **tracestate**) bằng metadata tùy chỉnh. Cách này phù hợp khi hệ thống đã dùng OpenTelemetry hoặc cần liên thông với HTTP/gRPC. MIME type tùy chỉnh phải được thống nhất giữa hai phía và có phiên bản rõ ràng.

Ví dụ mô hình hóa metadata tracing ở cấp ứng dụng:

~~~java
public record TraceContextMetadata(
        String traceparent,
        String tracestate) {
}
~~~

Định nghĩa MIME type riêng cho metadata này:

~~~java
private static final MimeType TRACE_CONTEXT_MIME_TYPE =
        MimeType.valueOf("message/vnd.acme.trace-context.v1");
~~~

Khi gửi request, lấy context hiện tại từ tracing API của ứng dụng rồi mã hóa thành metadata:

~~~java
TraceContextMetadata traceMetadata =
        traceContextProvider.currentMetadata();

Mono<Order> response = requester.route("orders.find")
        .metadata(traceMetadata, TRACE_CONTEXT_MIME_TYPE)
        .data(new OrderQuery("ORD-1042"))
        .retrieveMono(Order.class);
~~~

**traceContextProvider** đại diện cho lớp tích hợp với OpenTelemetry hoặc tracing framework mà ứng dụng đang dùng. Không tự tạo traceparent bằng cách ghép các chuỗi tùy ý; hãy để tracing SDK sinh và xác thực định dạng context.

Ở phía server, đăng ký metadata extractor để chuyển entry thành header của message:

~~~java
@Configuration
class RSocketMetadataConfiguration {

    @Bean
    RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
                .metadataExtractorRegistry(registry ->
                        registry.metadataToExtract(
                                TRACE_CONTEXT_MIME_TYPE,
                                TraceContextMetadata.class,
                                "traceContext"
                        ))
                // Đăng ký encoder/decoder cho TraceContextMetadata
                // nếu codec mặc định của ứng dụng chưa hỗ trợ kiểu này.
                .build();
    }
}
~~~

Handler có thể nhận metadata đã được giải mã:

~~~java
@MessageMapping("orders.find")
public Mono<Order> find(
        @Payload OrderQuery query,
        @Header("traceContext") TraceContextMetadata traceContext) {

    return orderService.find(query.orderId());
}
~~~

Ví dụ trên tập trung vào ranh giới metadata. Để trace thực sự tiếp tục qua các service, ứng dụng phải trích xuất context vào tracing SDK trước khi tạo span xử lý, sau đó inject context mới khi gửi request tiếp theo. Chỉ đọc traceparent vào một biến hoặc ghi nó vào log chưa đủ để tạo distributed trace.

### 3.3. Correlation ID cho log và phản hồi lỗi

Correlation ID hữu ích khi cần tìm log của một request mà không triển khai toàn bộ distributed tracing. Ví dụ, client tạo một request ID duy nhất và gửi nó trong metadata:

~~~java
private static final MimeType CORRELATION_ID_MIME_TYPE =
        MimeType.valueOf("message/vnd.acme.correlation-id.v1");

Mono<Order> response = requester.route("orders.find")
        .metadata(requestId, CORRELATION_ID_MIME_TYPE)
        .data(new OrderQuery("ORD-1042"))
        .retrieveMono(Order.class);
~~~

Server ghi correlation ID vào log cùng route, kết quả xử lý và mã lỗi. Nếu client gọi lại request, hãy quyết định request ID mới hay giữ ID cũ theo mục đích quan sát. Với retry, có thể dùng một correlation ID cho cả hành trình retry và tạo attempt ID riêng cho từng lần thử.

Correlation ID là dữ liệu do client cung cấp nên cần giới hạn độ dài và loại ký tự trước khi đưa vào log. Không đưa trực tiếp chuỗi chưa kiểm soát vào log format hoặc câu truy vấn.

## 4. Metadata ngữ cảnh của request

Metadata có thể truyền các giá trị xuyên qua nhiều tầng mà không phải lặp lại trong mọi DTO nghiệp vụ. Những giá trị thường gặp gồm:

| Thông tin | Ví dụ | Lưu ý |
|---|---|---|
| Tenant context | **tenant-42** | Server phải kiểm tra quyền truy cập tenant |
| Locale | **vi-VN** | Chỉ là gợi ý định dạng/ngôn ngữ; không dùng làm quy tắc bảo mật |
| Client version | **mobile-5.4.1** | Hữu ích cho tương thích và quan sát |
| Deadline | Thời điểm request hết hạn | Server cần giới hạn deadline tối đa |
| Idempotency key | **create-order-8f...** | Phải gắn với phạm vi người dùng/tenant và lưu trạng thái xử lý |
| Correlation ID | **req-...** | Dùng nối log; cần kiểm tra độ dài |
| Trace context | **traceparent**, **tracestate** | Phải được tracing SDK xử lý đúng chuẩn |

Không nên đưa mọi thông tin có thể nghĩ ra vào metadata. Mỗi entry tạo thêm chi phí mã hóa, truyền tải, giải mã và kiểm tra. Chỉ truyền giá trị cần thiết cho request hiện tại.

### 4.1. Tách domain data khỏi context

Giả sử API tạo đơn hàng:

~~~java
public record CreateOrderCommand(
        String productId,
        int quantity) {
}
~~~

Data chỉ chứa thông tin cần để tạo đơn hàng. Tenant, locale, trace context và idempotency key được truyền riêng qua metadata:

~~~java
requester.route("orders.create")
        .metadata(new TenantMetadata("tenant-42"), TENANT_MIME_TYPE)
        .metadata(new RequestContext("vi-VN", "create-8f21"),
                REQUEST_CONTEXT_MIME_TYPE)
        .metadata(traceMetadata, TRACE_CONTEXT_MIME_TYPE)
        .data(new CreateOrderCommand("SKU-100", 2))
        .retrieveMono(Order.class);
~~~

Ở server, các metadata entry được giải mã thành header. Một lớp ở biên ứng dụng có thể xác minh và tổng hợp chúng thành context nội bộ:

~~~java
public record RequestContext(
        String tenantId,
        Locale locale,
        String idempotencyKey,
        String correlationId) {
}
~~~

Context nội bộ nên được tạo sau khi xác thực và kiểm tra quyền. Không nên chuyển thẳng object metadata chưa xác minh vào mọi service như thể nó đã đáng tin cậy.

### 4.2. Deadline và timeout

Timeout phía client giúp caller ngừng chờ, nhưng không tự động bảo đảm server dừng công việc. Với chuỗi nhiều service, có thể truyền deadline hoặc thời gian còn lại trong metadata để các tầng phía sau tránh tiếp tục xử lý một request đã hết hạn.

Khi nhận deadline, server cần:

- Kiểm tra định dạng và đơn vị thời gian.
- Giới hạn thời gian tối đa mà client được yêu cầu.
- Tính thời gian còn lại dựa trên đồng hồ phù hợp, có xét đến sai lệch clock nếu truyền timestamp tuyệt đối.
- Kết hợp deadline với timeout cục bộ và cancellation của reactive pipeline.
- Không để một client gửi deadline rất xa nhằm giữ tài nguyên vô hạn.

Nếu truyền thời gian còn lại thay vì timestamp tuyệt đối, mỗi service cần trừ thời gian đã tiêu thụ trước khi chuyển tiếp. Nếu truyền timestamp, các máy phải đồng bộ đồng hồ đủ tốt và áp dụng giới hạn an toàn.

### 4.3. Idempotency key

RSocket có thể được dùng trong môi trường mạng không ổn định, nơi client không biết server đã xử lý xong request hay chưa khi connection bị ngắt. Với thao tác tạo đơn hàng hoặc thanh toán, client có thể gửi idempotency key để server nhận biết các lần gửi lại cùng một ý định.

Server nên kết hợp key với danh tính đã xác thực và phạm vi tenant, lưu trạng thái xử lý cùng kết quả, đồng thời xử lý an toàn các request đến đồng thời. Một key do client gửi không tự tạo ra idempotency; server phải thực thi quy tắc chống xử lý trùng.

## 5. Cấu hình composite metadata trong Spring RSocket

Khi một request cần nhiều metadata entry, requester phải sử dụng metadata MIME type tương thích với composite metadata:

~~~java
MimeType compositeMimeType =
        MimeType.valueOf("message/x.rsocket.composite-metadata.v0");

RSocketRequester requester = RSocketRequester.builder()
        .metadataMimeType(compositeMimeType)
        .connectTcp("localhost", 7000)
        .block();
~~~

Sau đó, mỗi request có thể thêm nhiều entry với MIME type tương ứng:

~~~java
requester.route("orders.find")
        .metadata(new TenantMetadata("tenant-42"), TENANT_MIME_TYPE)
        .metadata(traceMetadata, TRACE_CONTEXT_MIME_TYPE)
        .metadata(requestId, CORRELATION_ID_MIME_TYPE)
        .data(new OrderQuery("ORD-1042"))
        .retrieveMono(Order.class);
~~~

Phía server cần đăng ký metadata extractor cho từng MIME type ứng dụng muốn chuyển thành message header:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
        .metadataExtractorRegistry(registry -> {
            registry.metadataToExtract(
                    TENANT_MIME_TYPE,
                    TenantMetadata.class,
                    "tenant");
            registry.metadataToExtract(
                    TRACE_CONTEXT_MIME_TYPE,
                    TraceContextMetadata.class,
                    "traceContext");
            registry.metadataToExtract(
                    CORRELATION_ID_MIME_TYPE,
                    String.class,
                    "correlationId");
        })
        // Bổ sung encoder/decoder cho các kiểu metadata tùy chỉnh.
        .build();
~~~

Tên header (**tenant**, **traceContext**, **correlationId**) là tên ứng dụng lựa chọn. Handler dùng các tên này để nhận metadata:

~~~java
@MessageMapping("orders.find")
public Mono<Order> find(
        @Payload OrderQuery query,
        @Header("tenant") TenantMetadata tenant,
        @Header("correlationId") String correlationId,
        Principal principal) {

    log.info("order lookup tenant={} request={}",
            tenant.tenantId(), correlationId);

    return orderService.findForTenant(
            principal.getName(),
            tenant.tenantId(),
            query.orderId());
}
~~~

Đây là ví dụ minh họa cấu trúc tích hợp. Các record metadata tùy chỉnh cần codec tương ứng được đăng ký trong **RSocketStrategies**; client và server phải dùng cùng định dạng dữ liệu và MIME type. Với correlation ID dạng chuỗi, hãy bảo đảm decoder hỗ trợ MIME type tùy chỉnh hoặc dùng một metadata codec rõ ràng thay vì dựa vào giả định về codec mặc định.

## 6. Metadata trong các interaction model

Metadata đi cùng payload nên có thể được sử dụng với các interaction model của RSocket. Tuy nhiên, vị trí và tần suất truyền cần phù hợp với semantics của từng model.

| Interaction | Cách dùng metadata thường gặp |
|---|---|
| Fire-and-forget | Metadata xác thực, tenant, correlation ID hoặc idempotency key của lệnh |
| Request-response | Metadata xác thực, route, trace context và deadline của một request |
| Request-stream | Metadata khởi tạo stream như filter, tenant và trace context; cân nhắc metadata trên từng message nếu giao thức ứng dụng cần |
| Request-channel | Metadata ở payload đầu tiên để khởi tạo channel; các payload tiếp theo có thể mang metadata riêng nếu từng message cần context riêng |

Với stream dài hạn, cần phân biệt metadata khởi tạo stream với metadata của từng phần tử. Ví dụ, tenant và bộ lọc có thể cố định cho cả stream, trong khi correlation ID hoặc sequence number có thể thay đổi theo từng message. Đừng gửi lại token hoặc toàn bộ context lớn trên mọi phần tử nếu không cần thiết.

Một sơ đồ request-response điển hình:

~~~mermaid
sequenceDiagram
    participant C as RSocket client
    participant S as RSocket server
    participant A as Security layer
    participant H as Message handler
    participant D as Domain service
    C->>S: SETUP (metadata MIME type, setup auth)
    C->>S: REQUEST_RESPONSE (data + composite metadata)
    S->>A: Xác minh credential
    A-->>S: Principal đã xác thực
    S->>H: Payload + metadata headers + Principal
    H->>D: Kiểm tra quyền và xử lý domain
    D-->>H: Kết quả
    H-->>C: PAYLOAD (data response)
~~~

Metadata có thể không xuất hiện trong mọi response. Nếu client cần correlation ID hoặc trace context ở chiều trả về, ứng dụng phải xác định rõ cách phản hồi hoặc inject context vào tracing framework; không giả định server tự động sao chép metadata request sang response.

## 7. Bảo vệ metadata

Metadata có thể chứa credential, tenant context và thông tin vận hành. Hãy coi nó là dữ liệu đầu vào từ mạng và áp dụng chính sách bảo vệ như với payload.

### 7.1. Bảo vệ đường truyền

Bearer token và metadata nhạy cảm phải được truyền qua kết nối được bảo vệ bằng TLS, ví dụ RSocket qua TCP có TLS hoặc RSocket qua WebSocket bảo mật (**wss**). Nếu dùng plaintext, người có khả năng quan sát đường truyền có thể đọc credential và dữ liệu.

TLS bảo vệ đường truyền giữa hai đầu kết nối. Nó không thay thế xác thực, phân quyền, kiểm tra tenant hoặc bảo vệ dữ liệu trong log và hệ thống quan sát.

### 7.2. Không ghi credential vào log

Không log bearer token, password, session secret hoặc toàn bộ metadata section. Log chỉ nên chứa các trường đã được chọn lọc và làm sạch, chẳng hạn route, correlation ID đã kiểm tra, tenant ID sau khi xác minh và trạng thái xác thực.

Nếu cần debug metadata, hãy ghi tên MIME type, kích thước entry và trạng thái giải mã. Không dump byte hoặc chuỗi credential vào log.

### 7.3. Giới hạn kích thước và kiểm tra đầu vào

Metadata được truyền trong frame nên tiêu tốn băng thông và bộ nhớ. Server cần giới hạn:

- Tổng kích thước metadata và kích thước từng entry.
- Độ dài tenant ID, correlation ID và các chuỗi định danh.
- Số lượng metadata entry được chấp nhận.
- Định dạng, charset và phiên bản schema.
- Các giá trị deadline, locale và client version.

Từ chối metadata sai định dạng hoặc vượt giới hạn càng sớm càng tốt. Tránh parse metadata không giới hạn trước khi xác thực hoặc tạo buffer có kích thước tùy ý từ giá trị client gửi.

### 7.4. Phiên bản hóa MIME type tùy chỉnh

Đối với metadata do ứng dụng định nghĩa, nên dùng MIME type có namespace và phiên bản:

~~~text
message/vnd.acme.tenant.v1
message/vnd.acme.trace-context.v1
message/vnd.acme.correlation-id.v1
~~~

Khi thay đổi cấu trúc không tương thích, phát hành phiên bản mới hoặc có quy tắc tương thích rõ ràng. Không âm thầm thay đổi ý nghĩa của cùng một MIME type vì client và server có thể được triển khai ở thời điểm khác nhau.

### 7.5. Không biến metadata thành nơi chứa mọi thứ

Metadata nên nhỏ, có cấu trúc và có mục đích rõ ràng. Tệp lớn, danh sách nghiệp vụ, ảnh hoặc nội dung domain thuộc data hoặc một kênh lưu trữ phù hợp. Đưa dữ liệu lớn vào metadata làm tăng chi phí parse và có thể vượt giới hạn frame.

## 8. Lỗi thường gặp và cách xử lý

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Hai phía dùng MIME type khác nhau | Metadata không được giải mã hoặc bị bỏ qua | Thống nhất MIME type và codec |
| Gửi nhiều entry nhưng không dùng composite metadata | Bên nhận không biết cách phân tách entry | Cấu hình composite metadata ở cả hai phía |
| Dùng tenant ID từ client như danh tính | Truy cập chéo tenant | Liên kết tenant với Principal đã xác thực |
| Log toàn bộ metadata | Lộ token hoặc dữ liệu nhạy cảm | Chỉ log trường đã chọn lọc và làm sạch |
| Tạo trace ID mới ở mỗi service | Trace bị đứt thành nhiều phần | Extract và inject context bằng tracing SDK |
| Chỉ truyền correlation ID rồi kỳ vọng có span | Không có distributed trace đầy đủ | Dùng tracing SDK và tạo span ở từng service |
| Gửi context lớn trên mọi message stream | Tăng băng thông và chi phí giải mã | Chỉ gửi context thay đổi theo message |
| Dùng setup metadata cho dữ liệu thay đổi từng request | Context cũ có thể bị dùng sai | Đưa dữ liệu biến động vào request metadata |
| Bỏ qua version của custom metadata | Khó nâng cấp client/server độc lập | Version hóa MIME type và codec |

## 9. Checklist thiết kế metadata

Trước khi đưa metadata vào production, hãy xác nhận:

1. Mỗi metadata entry có mục đích, MIME type và schema rõ ràng.
2. Setup metadata và request metadata được dùng đúng phạm vi vòng đời.
3. Credential được xác minh ở server; authorization dựa trên Principal đã xác thực.
4. Tenant context do client gửi được kiểm tra quyền trước khi truy cập dữ liệu.
5. Trace context được extract/inject bằng tracing SDK, không chỉ được ghi vào log.
6. Correlation ID và các chuỗi client gửi được giới hạn độ dài và làm sạch.
7. Metadata nhạy cảm đi qua TLS và không bị ghi vào log.
8. Tổng kích thước metadata, số entry và schema đều có giới hạn.
9. Custom MIME type có namespace và version để hỗ trợ triển khai độc lập.
10. Với stream dài hạn, xác định rõ context nào cố định cho stream và context nào thay đổi theo message.

## 10. Tổng kết

RSocket payload tách data nghiệp vụ khỏi metadata dùng để định tuyến, xác thực, truy vết và mang ngữ cảnh. Setup metadata phù hợp với thông tin gắn với connection; request metadata phù hợp với thông tin thay đổi theo từng interaction. Composite metadata cho phép nhiều entry với MIME type riêng trong cùng payload.

Đối với bảo mật, server phải xác minh credential và phân quyền dựa trên danh tính đã xác thực. Đối với tracing, cần truyền trace context và để tracing SDK tạo span qua từng service. Đối với context, tenant, deadline, locale, correlation ID và idempotency key phải có schema, giới hạn và quy tắc tin cậy rõ ràng. Khi thiết kế metadata nhỏ gọn, có phiên bản và được kiểm tra ở biên hệ thống, RSocket có thể mang đủ ngữ cảnh vận hành mà vẫn giữ data model nghiệp vụ rõ ràng.
