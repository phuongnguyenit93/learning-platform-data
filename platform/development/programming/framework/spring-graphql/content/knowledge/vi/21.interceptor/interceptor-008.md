# Correlation ID trong interceptor

Trong một request GraphQL, một thao tác có thể đi qua web transport, interceptor, GraphQL execution, resolver, DataLoader và nhiều service downstream. Khi xảy ra lỗi hoặc độ trễ, chỉ nhìn log của một thành phần thường không đủ để biết các sự kiện đó thuộc cùng request hay không. **Correlation ID** là mã định danh được gắn với một request để các lớp trong ứng dụng và các dịch vụ liên quan có thể liên kết log, trace và sự kiện xử lý.

Với Spring for GraphQL, một nơi phù hợp để nhận hoặc tạo Correlation ID là WebGraphQlInterceptor. Interceptor có thể đưa ID vào GraphQLContext trước khi operation được thực thi. Resolver, batch loader và các thành phần khác trong cùng execution sau đó đọc cùng giá trị mà không cần phụ thuộc trực tiếp vào HTTP request.

Correlation ID hỗ trợ quan sát và chẩn đoán. Nó không phải thông tin xác thực, không thay thế authorization, distributed tracing hay idempotency key.

## 1. Correlation ID là gì?

Correlation ID là một định danh gắn với một request hoặc một luồng xử lý nghiệp vụ để kết nối các log và sự kiện có liên quan. Ví dụ, một GraphQL request gọi resolver lấy đơn hàng, sau đó gọi service khách hàng và service thanh toán. Nếu các lớp đều ghi cùng Correlation ID, người vận hành có thể lọc log theo ID để xem toàn bộ hành trình.

Một Correlation ID tốt có các đặc điểm:

- Duy nhất với xác suất va chạm rất thấp trong phạm vi hệ thống.
- Ngắn gọn, dễ truyền qua HTTP header và dễ tìm trong log.
- Không chứa thông tin cá nhân, token, tenant secret hoặc dữ liệu nghiệp vụ nhạy cảm.
- Được giữ nhất quán trong suốt một request và được truyền sang các lời gọi downstream khi phù hợp.
- Được kiểm tra định dạng và giới hạn độ dài nếu nhận từ client hoặc proxy.

Ứng dụng thường dùng UUID ngẫu nhiên làm giá trị mới khi request chưa có ID đáng tin cậy. Không nên tạo ID từ email, user ID, số điện thoại hoặc dữ liệu có thể tiết lộ danh tính.

## 2. Phân biệt Correlation ID, Request ID, Trace ID và Idempotency Key

Các loại ID này có thể cùng xuất hiện trong một hệ thống nhưng phục vụ mục đích khác nhau:

| Giá trị | Mục đích | Phạm vi điển hình |
| --- | --- | --- |
| Request ID | Nhận diện một lần nhận request ở một service | Một HTTP request hoặc một lần xử lý tại service |
| Correlation ID | Liên kết log/sự kiện của cùng một luồng nghiệp vụ | Có thể đi qua nhiều service và nhiều request |
| Trace ID | Liên kết các span trong một distributed trace | Một trace, gồm nhiều service/span |
| Span ID | Nhận diện một đoạn công việc trong trace | Một operation hoặc lời gọi cụ thể |
| Idempotency Key | Nhận diện một ý định command để chống side effect lặp | Một thao tác nghiệp vụ và các lần retry của nó |

W3C Trace Context định nghĩa header traceparent để truyền trace ID và parent span ID giữa các thành phần. Khi ứng dụng dùng Micrometer Tracing hoặc OpenTelemetry, nên để tracing framework quản lý trace/span và propagation. Correlation ID có thể là một ID ứng dụng bổ sung, hoặc có thể dùng trace ID làm trường tìm kiếm chung nếu chính sách quan sát của hệ thống cho phép.

Không nên tự ghi đè traceparent bằng một Correlation ID tùy ý. Trace ID có định dạng và vòng đời riêng, còn Correlation ID là quy ước của ứng dụng.

Idempotency Key cũng khác Correlation ID. Khi client retry cùng một mutation, mỗi lần gửi có thể là một HTTP request mới và có Correlation ID mới, nhưng vẫn phải dùng cùng Idempotency Key để server nhận ra đó là cùng một command. Ngược lại, một request GraphQL có thể chứa nhiều field nhưng thường chỉ có một Correlation ID cho execution đó.

## 3. Vì sao đặt xử lý Correlation ID ở WebGraphQlInterceptor?

WebGraphQlInterceptor nằm ở tầng web của Spring for GraphQL. Nó nhận WebGraphQlRequest trước khi GraphQL operation được thực thi, vì vậy có thể:

- Đọc header như X-Correlation-Id hoặc X-Request-Id.
- Kiểm tra định dạng và quyết định giữ hay thay giá trị đầu vào.
- Tạo UUID nếu request chưa có ID hợp lệ.
- Đưa ID vào GraphQLContext qua configureExecutionInput.
- Bổ sung ID vào response header để client gửi kèm khi báo lỗi.
- Ghi log hoặc metrics quanh thời gian xử lý web GraphQL request.

Resolver không nên phụ thuộc trực tiếp vào ServletRequest hay HTTP headers. Đưa metadata vào GraphQLContext tạo ra ranh giới rõ ràng giữa transport và GraphQL execution. Cách này cũng giúp resolver có thể được kiểm thử mà không cần mô phỏng toàn bộ HTTP request.

Luồng xử lý:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[WebGraphQlRequest]
    B --> C[WebGraphQlInterceptor]
    C --> D[Đọc hoặc tạo Correlation ID]
    D --> E[Đưa ID vào GraphQLContext]
    E --> F[GraphQL execution]
    F --> G[Resolver và DataLoader]
    G --> H[Service và downstream client]
    H --> I[Log cùng Correlation ID]
    I --> J[GraphQL response + response header]
~~~

WebGraphQlInterceptor áp dụng cho web transport tương ứng. Nếu ứng dụng dùng WebSocket, cần xem xét WebSocketGraphQlInterceptor và phân biệt metadata cấp connection với metadata của từng GraphQL operation.

## 4. Tạo hoặc xác thực Correlation ID

Một policy đơn giản là nhận header X-Correlation-Id nếu giá trị có định dạng cho phép; nếu thiếu hoặc không hợp lệ thì tạo UUID mới. Ví dụ sau giới hạn ID ở 64 ký tự chữ, số, dấu chấm, gạch dưới và gạch ngang:

~~~java
private static final Pattern SAFE_ID =
    Pattern.compile("[A-Za-z0-9._-]{1,64}");

private String resolveCorrelationId(String incoming) {
    if (incoming != null && SAFE_ID.matcher(incoming).matches()) {
        return incoming;
    }
    return UUID.randomUUID().toString();
}
~~~

Đây là một chính sách minh họa. Hệ thống có thể chọn từ chối request khi header sai định dạng thay vì tạo ID mới, nhưng phải quy định hành vi nhất quán. Nếu ID do gateway nội bộ tạo, chỉ giữ nguyên ID khi request thực sự đến từ gateway đáng tin cậy và hạ tầng đã loại bỏ header giả do client bên ngoài gửi.

Không nên tin bất kỳ giá trị header nào như một danh tính hoặc bằng chứng quyền truy cập. Client có thể tự đặt X-Correlation-Id. Giá trị này chỉ phục vụ liên kết log, nên việc giả mạo nó không được làm thay đổi tenant, principal hoặc authorization.

Không cho phép ID quá dài, chứa ký tự điều khiển hoặc xuống dòng. Điều này giúp tránh log injection, header parsing bất thường và dữ liệu log khó tìm. Không phản chiếu nguyên trạng một header chưa được kiểm tra vào response hoặc log.

## 5. Cài đặt WebGraphQlInterceptor

Ví dụ sau đọc header, tạo ID nếu cần, đưa giá trị vào GraphQLContext và trả lại ID trong response header:

~~~java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CorrelationIdInterceptor implements WebGraphQlInterceptor {

    public static final String HEADER_NAME = "X-Correlation-Id";
    public static final String CONTEXT_KEY = "correlationId";

    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        String correlationId = resolveCorrelationId(
            request.getHeaders().getFirst(HEADER_NAME));

        request.configureExecutionInput((input, builder) ->
            builder.graphQLContext(context ->
                context.put(CONTEXT_KEY, correlationId)
            ).build()
        );

        return chain.next(request)
            .doOnNext(response ->
                response.getResponseHeaders().set(HEADER_NAME, correlationId));
    }

    private String resolveCorrelationId(String incoming) {
        if (incoming != null && SAFE_ID.matcher(incoming).matches()) {
            return incoming;
        }
        return UUID.randomUUID().toString();
    }
}
~~~

Các phần chính:

1. getHeaders().getFirst(...) đọc header từ WebGraphQlRequest.
2. resolveCorrelationId kiểm tra định dạng và tạo UUID khi cần.
3. configureExecutionInput bổ sung correlationId vào GraphQLContext trước khi operation chạy.
4. chain.next(request) chuyển request sang interceptor tiếp theo hoặc GraphQL service.
5. doOnNext thêm cùng ID vào response header sau khi có response.

Đoạn code dùng API response headers của WebGraphQlResponse. Khi triển khai, hãy kiểm tra đúng phiên bản Spring for GraphQL mà dự án đang dùng và bảo đảm response header được adapter transport chuyển ra HTTP response như mong muốn.

Nếu interceptor khác cũng cần Correlation ID, có thể đặt thứ tự bằng @Order hoặc thiết kế một interceptor metadata tổng hợp. Tránh để nhiều interceptor tự tạo ID hoặc ghi đè cùng context key.

## 6. Đọc Correlation ID trong resolver

Spring for GraphQL hỗ trợ @ContextValue để bind một giá trị từ GraphQLContext vào tham số controller:

~~~java
@Controller
public class OrderQueryController {

    private static final Logger log =
        LoggerFactory.getLogger(OrderQueryController.class);

    private final OrderService orderService;

    public OrderQueryController(OrderService orderService) {
        this.orderService = orderService;
    }

    @QueryMapping
    public Order orderById(
            @Argument("id") String id,
            @ContextValue("correlationId") String correlationId) {

        log.info("Loading order, correlationId={}", correlationId);
        return orderService.findById(id);
    }
}
~~~

Nếu resolver cần nhiều thông tin execution, có thể nhận DataFetchingEnvironment:

~~~java
@QueryMapping
public Order orderById(
        @Argument("id") String id,
        DataFetchingEnvironment environment) {

    String correlationId = environment.getGraphQlContext()
        .get("correlationId");
    return orderService.findById(id);
}
~~~

@ContextValue lấy dữ liệu server đã gắn vào execution context. Nó khác @Argument, vốn lấy dữ liệu do client truyền cho field. Client không thể ghi đè correlationId trong GraphQLContext bằng cách gửi một variable hoặc argument cùng tên.

Nếu context key có thể vắng mặt trong một số test hoặc transport, có thể khai báo tham số không bắt buộc theo thuộc tính required của @ContextValue và xử lý null phù hợp. Với interceptor trên, ID luôn được tạo nên resolver có thể kỳ vọng key tồn tại khi request đi qua đúng interceptor.

## 7. Truyền Correlation ID vào DataLoader và batch loader

Batch loader có thể cần ghi log khi tải một nhóm key. Spring for GraphQL cho phép batch loader nhận BatchLoaderEnvironment và đọc context của execution theo API tương ứng:

~~~java
registry.forTypePair(Long.class, Author.class)
    .registerMappedBatchLoader((authorIds, environment) -> {
        GraphQLContext context = (GraphQLContext) environment.getContext();
        String correlationId = context.get("correlationId");

        log.debug("Loading authors, count={}, correlationId={}",
            authorIds.size(), correlationId);

        return authorService.findAllByIdsAsync(authorIds);
    });
~~~

Trong ví dụ, loader nhận cùng ID mà interceptor đã đưa vào GraphQLContext. Cần dùng đúng kiểu context và API BatchLoaderEnvironment của phiên bản GraphQL Java/Spring for GraphQL đang sử dụng.

Không lưu Correlation ID vào singleton field hoặc static mutable variable để resolver và batch loader đọc. Nhiều request có thể chạy đồng thời; biến dùng chung sẽ bị ghi đè và làm log gắn nhầm ID. Dữ liệu request phải đi theo GraphQLContext, Reactor Context hoặc cơ chế context propagation được thiết kế rõ ràng.

## 8. Truyền ID đến service và downstream HTTP call

Một cách dễ kiểm soát là truyền Correlation ID tường minh từ resolver vào service khi service cần gọi hệ thống khác:

~~~java
@QueryMapping
public CompletableFuture<OrderView> orderById(
        @Argument("id") String id,
        @ContextValue("correlationId") String correlationId) {
    return orderService.findView(id, correlationId);
}
~~~

Service có thể thêm header vào WebClient:

~~~java
public CompletableFuture<Customer> findCustomer(
        String customerId, String correlationId) {

    return webClient.get()
        .uri("/customers/{id}", customerId)
        .header("X-Correlation-Id", correlationId)
        .retrieve()
        .bodyToMono(Customer.class)
        .toFuture();
}
~~~

Truyền tường minh giúp thấy rõ dependency và không phụ thuộc ThreadLocal. Nếu hệ thống dùng Micrometer Tracing hoặc OpenTelemetry, hãy bật propagation chuẩn để trace context được tự động truyền qua WebClient. Correlation ID ứng dụng có thể được thêm riêng khi downstream cần liên kết log theo quy ước nội bộ.

Khi gọi nhiều downstream, hãy truyền cùng Correlation ID cho những lời gọi thuộc cùng request. Nếu downstream tạo request mới cho một luồng nghiệp vụ độc lập, cần thống nhất liệu giữ Correlation ID gốc hay tạo ID mới và liên kết bằng trace context hoặc business operation ID.

## 9. Correlation ID trong async và reactive flow

Spring for GraphQL dùng reactive API ở tầng web. WebGraphQlInterceptor trả về Mono<WebGraphQlResponse>, và request có thể tiếp tục qua các operator hoặc resolver bất đồng bộ trước khi response hoàn tất.

Không nên dùng ThreadLocal làm nơi lưu Correlation ID rồi giả định mọi callback sẽ đọc được giá trị đó. CompletableFuture có thể chạy trên thread pool khác; Reactor có thể chuyển scheduler. ThreadLocal/MDC không tự động luôn theo execution.

Các lựa chọn an toàn hơn:

- Đưa ID vào GraphQLContext để resolver và DataLoader đọc theo execution.
- Truyền ID tường minh vào service hoặc client khi cần gọi downstream.
- Dùng Reactor Context cho metadata cần đi theo reactive subscriber chain.
- Dùng Micrometer Context Propagation hoặc cơ chế tương thích để truyền MDC/SecurityContext qua executor khi thực sự cần.
- Dùng Micrometer Tracing/OpenTelemetry cho trace/span context thay vì tự xây dựng propagation distributed tracing.

Không gọi block() trong WebGraphQlInterceptor hoặc trên event-loop thread. Giữ chain reactive bằng cách trả Mono từ chain.next và nối operator phù hợp.

## 10. Gắn Correlation ID vào MDC và structured logging

MDC giúp log framework tự thêm một số trường vào mỗi log event. Tuy nhiên, MDC truyền thống dựa trên ThreadLocal. Một cách đặt rồi xóa MDC quanh lời gọi reactive như sau có thể sai:

~~~java
MDC.put("correlationId", correlationId);
return chain.next(request)
    .doFinally(signal -> MDC.remove("correlationId"));
~~~

Lời gọi chain.next có thể trả Mono ngay trước khi pipeline thực sự hoàn tất. Việc remove có thể xảy ra trên một thread khác hoặc trước khi các callback cần log chạy. Cách này không bảo đảm context được giữ đúng.

Nếu cần MDC, hãy dùng context propagation được hỗ trợ bởi stack logging/observability của ứng dụng. Với Reactor, có thể dùng Micrometer Context Propagation và cấu hình tương thích để ánh xạ Reactor Context sang MDC. Với executor cho CompletableFuture, có thể dùng TaskDecorator hoặc executor được bọc để capture/restore context. Phải bảo đảm context được khôi phục và dọn dẹp sau callback để tránh rò ID giữa các tác vụ trên cùng thread.

Một lựa chọn đơn giản là ghi correlationId như một structured logging field tại nơi đã có giá trị:

~~~java
log.info("Order lookup started, correlationId={}, orderId={}",
    correlationId, orderId);
~~~

Không ghi raw GraphQL variables, token, cookie hoặc dữ liệu thanh toán chỉ để có thêm ngữ cảnh. Correlation ID nên là trường log có thể tìm kiếm, không phải metric tag có cardinality cao.

## 11. Bảo mật và tin cậy của ID đầu vào

Correlation ID do client gửi có thể bị giả mạo. Kẻ gọi API có thể cố tình dùng cùng ID cho nhiều request để làm nhiễu log hoặc tạo khó khăn khi điều tra. Vì vậy:

- Không dùng Correlation ID để xác định user, tenant, role hoặc quyền truy cập.
- Giới hạn độ dài và tập ký tự được chấp nhận.
- Không cho phép CR/LF hoặc ký tự điều khiển để tránh log/header injection.
- Chỉ tin ID do gateway tạo khi kết nối đến từ gateway đáng tin cậy và header bên ngoài đã được xử lý.
- Nếu ID không hợp lệ, tạo ID mới hoặc từ chối theo policy; không ghi giá trị độc hại vào log.
- Không nhúng thông tin cá nhân hay bí mật vào ID.
- Không dùng Correlation ID làm khóa idempotency hoặc khóa cache bảo mật.

Nếu trả ID trong response header, chỉ phản chiếu giá trị đã kiểm tra hoặc ID mới do server tạo. Response header giúp client cung cấp ID khi báo lỗi cho đội vận hành.

## 12. Interceptor chain và nhiều loại transport

Một ứng dụng có thể có nhiều WebGraphQlInterceptor: một interceptor tạo Correlation ID, một interceptor xác định locale, một interceptor đo thời gian và một interceptor bổ sung metadata tenant. Chúng được nối thành chain; thứ tự quan trọng nếu interceptor sau cần dữ liệu interceptor trước đã thêm vào GraphQLContext.

Có thể dùng @Order để đặt thứ tự rõ ràng. Nên thống nhất tên context key, tránh ghi đè và giữ interceptor tập trung vào concern riêng. Nếu một interceptor kết thúc request sớm, cần quyết định response có chứa Correlation ID hay không.

Với WebSocket, connection có thể tồn tại qua nhiều GraphQL operation. Không nên dùng một Correlation ID duy nhất ở cấp connection cho mọi operation nếu mục tiêu là theo dõi từng request. Có thể có connection ID riêng, đồng thời tạo hoặc xác định Correlation ID cho mỗi operation/message theo giao thức và interceptor tương ứng. Connection state và GraphQLContext của từng execution là hai phạm vi khác nhau.

## 13. Kiểm thử Correlation ID

Nên kiểm thử interceptor ở tầng web để bảo đảm header được đọc, context được thiết lập và response header được trả lại. Kiểm thử resolver riêng lẻ bằng GraphQlTester không đủ chứng minh interceptor HTTP đã chạy.

Với HttpGraphQlTester được xây dựng từ WebTestClient, có thể gửi header như sau:

~~~java
HttpGraphQlTester tester = HttpGraphQlTester.builder(webTestClient)
    .headers(headers -> headers.set(
        "X-Correlation-Id", "test-request-001"))
    .build();
~~~

Sau đó gửi operation đi qua ứng dụng và dùng mock service hoặc spy để xác nhận resolver/service nhận được correlationId tương ứng. Nếu muốn kiểm tra response header, dùng WebTestClient trực tiếp hoặc API tester phù hợp để đọc HTTP response headers.

Các trường hợp nên kiểm tra:

- Header hợp lệ được giữ nguyên và xuất hiện trong GraphQLContext.
- Header bị thiếu thì server tạo UUID mới.
- Header quá dài hoặc chứa ký tự không cho phép bị thay bằng ID mới hoặc bị từ chối theo policy.
- Response trả lại ID đã được chấp nhận.
- Hai request đồng thời có ID riêng, không ghi đè context của nhau.
- Resolver và DataLoader trong cùng execution đọc cùng ID.
- Downstream client nhận header đúng khi được truyền correlationId.
- Lỗi ở resolver vẫn có log gắn đúng ID.
- Interceptor không gọi block() và không làm hỏng reactive chain.

Không nên chỉ kiểm tra rằng response có header. Cần xác nhận cùng ID được truyền xuyên suốt tới thành phần thực thi mà bạn muốn quan sát.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Resolver không thấy Correlation ID | Interceptor chưa gọi configureExecutionInput hoặc dùng key khác | Kiểm tra key và thời điểm thiết lập trước chain.next |
| Mỗi lớp log một ID khác nhau | Nhiều nơi tự tạo ID hoặc ghi đè context | Tạo một lần tại ranh giới request và truyền tiếp |
| ID mất khi chạy CompletableFuture | Dựa vào ThreadLocal/MDC qua thread khác | Truyền tường minh hoặc cấu hình context propagation |
| ID mất ở downstream | Client HTTP chưa thêm header hoặc tracing propagation chưa cấu hình | Truyền ID qua WebClient hoặc dùng tracing instrumentation |
| Log bị gắn nhầm ID giữa request | Dùng static/singleton mutable state | Dùng GraphQLContext/Reactive Context theo execution |
| Log injection hoặc header lỗi | Chấp nhận ID đầu vào không kiểm tra | Giới hạn ký tự, độ dài và không phản chiếu raw value |
| Trace UI không nhóm request như mong muốn | Nhầm Correlation ID với traceparent/trace ID | Dùng Micrometer Tracing/OpenTelemetry cho distributed tracing |
| Metric tăng cardinality rất cao | Dùng ID duy nhất làm metric tag | Đưa ID vào log/trace; metric chỉ dùng tag có cardinality giới hạn |

## 15. Nguyên tắc thiết kế

Tạo hoặc xác thực Correlation ID ở ranh giới web request, sau đó đưa vào GraphQLContext bằng WebGraphQlInterceptor. Dùng @ContextValue hoặc DataFetchingEnvironment để resolver đọc ID; truyền tường minh vào service và downstream client khi cần. Với DataLoader, dùng context của execution thay vì biến dùng chung.

Phân biệt Correlation ID với trace ID, request ID và idempotency key. Dùng Micrometer Tracing hoặc OpenTelemetry để truyền distributed trace context; không tự thay thế W3C traceparent bằng một header tùy ý. Không dùng ID để quyết định quyền truy cập và không ghi dữ liệu nhạy cảm vào ID hoặc log.

Khi có async/reactive flow, tránh phụ thuộc ThreadLocal và bảo đảm MDC/context propagation theo đúng scheduler hoặc executor. Kiểm thử cả đường đi từ HTTP header đến resolver, batch loader, downstream call và response header.

Correlation ID là một chi tiết nhỏ ở ranh giới request nhưng đem lại giá trị lớn khi điều tra sự cố. Trong Spring for GraphQL, WebGraphQlInterceptor và GraphQLContext tạo ra một đường truyền rõ ràng để các thành phần cùng execution sử dụng một ID mà không phụ thuộc vào transport hoặc thread cụ thể.
