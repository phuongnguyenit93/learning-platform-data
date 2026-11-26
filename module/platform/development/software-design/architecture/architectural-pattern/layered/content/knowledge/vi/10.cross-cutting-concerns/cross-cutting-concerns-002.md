# Truyền định danh người dùng, ngữ cảnh và mã tương quan qua các tầng

Bài học này thuộc module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED`, nhằm giúp người học tổ chức phần mềm theo kiến trúc phân tầng. Trong chương **Các mối quan tâm xuyên tầng**, ta tìm hiểu cách truyền danh tính người thực hiện, ngữ cảnh thực thi và mã tương quan qua các tầng. Đây là những thông tin có thể cần ở nhiều nơi như bảo mật, kiểm toán, ghi log và giao tiếp bất đồng bộ. Thiết kế đúng giúp các tầng nhận đủ thông tin cần thiết mà không phụ thuộc vào đối tượng HTTP, biến toàn cục hoặc cơ chế riêng của framework.

## 1. Phân biệt ba loại thông tin

Các khái niệm thường được gom chung dưới tên “request context”, nhưng chúng có mục đích khác nhau:

| Thông tin | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Định danh người thực hiện (actor identity) | Ai hoặc thành phần nào đang yêu cầu hành động? | User ID, service account, loại actor |
| Ngữ cảnh thực thi (execution context) | Yêu cầu này đang chạy trong phạm vi nào và cần những thông tin nào để xử lý? | Tenant ID, locale, múi giờ nghiệp vụ, quyền hoặc phạm vi đã xác minh |
| Mã tương quan (correlation ID) | Những log, sự kiện và lời gọi nào thuộc cùng một luồng xử lý? | `correlationId` gắn với yêu cầu tạo đơn hàng |

Ngoài ra còn có **trace ID** và **span ID** của distributed tracing. Trace ID liên kết các span trong một trace phân tán; span ID nhận diện một thao tác cụ thể trong trace. Correlation ID thường là mã ứng dụng hoặc mã nghiệp vụ được dùng để tìm các bản ghi liên quan. Hai loại ID có thể được liên kết với nhau, nhưng không nên mặc định chúng luôn giống nhau.

Ví dụ, một người dùng đã đăng nhập gửi yêu cầu xem đơn hàng trong tenant `tenant-42`. Hệ thống cần biết user nào thực hiện, yêu cầu thuộc tenant nào và log ở controller, application service, repository adapter cùng lời gọi dịch vụ khác phải có khả năng truy vết về cùng một yêu cầu. Các thông tin đó không có cùng mức độ tin cậy và không nên được truyền như một chuỗi tùy ý.

## 2. Định danh người dùng phải đến từ nguồn đã xác thực

Định danh actor thường được lấy từ kết quả xác thực đã được hệ thống kiểm tra, chẳng hạn principal do Spring Security cung cấp sau khi xác minh session hoặc token. Không nên coi `userId` trong query parameter, request body hay header do client tự gửi là danh tính đã xác thực.

Ví dụ, endpoint nhận yêu cầu hủy đơn hàng có thể lấy principal đã xác thực:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final CancelOrderUseCase cancelOrder;

    OrderController(CancelOrderUseCase cancelOrder) {
        this.cancelOrder = cancelOrder;
    }

    @PostMapping("/{orderId}/cancel")
    void cancel(
            @PathVariable String orderId,
            @RequestBody CancelOrderRequest request,
            @AuthenticationPrincipal AppPrincipal principal) {

        ActorContext actor = new ActorContext(
            new UserId(principal.userId()),
            new TenantId(principal.tenantId()),
            ActorKind.USER
        );

        cancelOrder.execute(new CancelOrderCommand(
            new OrderId(orderId), request.reason(), actor));
    }
}
```

`AppPrincipal` là kiểu principal do ứng dụng định nghĩa hoặc chuyển đổi từ danh tính đã xác thực. Ví dụ giả định tenant đã được xác minh trong quá trình đăng nhập hoặc trong bước kiểm tra membership. Không được lấy `tenantId` từ client rồi tin tưởng trực tiếp chỉ vì request đã có một user đăng nhập.

Đối với tác vụ nền, actor có thể là `SYSTEM` hoặc một service account thay vì người dùng. Vì vậy, mô hình actor nên biểu diễn được nguồn thực hiện hành động, không giả định mọi hoạt động đều bắt nguồn từ một user tương tác.

```java
public enum ActorKind {
    USER, SERVICE, SYSTEM
}

public record ActorContext(
    UserId actorId,
    TenantId tenantId,
    ActorKind kind
) {}
```

Đây là một kiểu minh họa. Có hệ thống cần thêm subject ID, client ID, delegated actor hoặc thông tin impersonation để phục vụ audit. Chỉ đưa những trường có ý nghĩa và đã được xác minh vào hợp đồng; tránh mang toàn bộ principal, JWT hoặc đối tượng `Authentication` xuyên qua mọi tầng.

## 3. Truyền ngữ cảnh qua hợp đồng ứng dụng

Khi một ca sử dụng cần biết actor hoặc tenant, hãy truyền chúng một cách tường minh qua command, query hoặc một đối tượng context có kiểu. Ví dụ:

```java
public record CancelOrderCommand(
    OrderId orderId,
    CancelReason reason,
    ActorContext actor
) {}
```

Application service có thể dùng actor để kiểm tra quyền và phối hợp hành động:

```java
@Service
class CancelOrderService implements CancelOrderUseCase {
    private final OrderRepository orders;
    private final OrderAccessPolicy accessPolicy;

    CancelOrderService(
            OrderRepository orders,
            OrderAccessPolicy accessPolicy) {
        this.orders = orders;
        this.accessPolicy = accessPolicy;
    }

    @Transactional
    public void execute(CancelOrderCommand command) {
        Order order = orders.findByIdAndTenantId(
                command.orderId(), command.actor().tenantId())
            .orElseThrow(() -> new OrderNotFoundException(command.orderId()));

        accessPolicy.requireCanCancel(command.actor(), order);
        order.cancel(command.reason());
        orders.save(order);
    }
}
```

Trong ví dụ, tầng ứng dụng phối hợp việc tải đơn theo tenant và kiểm tra quyền của actor. Đối tượng miền `Order` vẫn chịu trách nhiệm quyết định trạng thái hiện tại có cho phép hủy hay không. Nếu chính sách hủy thuộc nghiệp vụ, nó được thực thi trong mô hình miền; quyền truy cập một đơn hàng của một actor có thể được kiểm tra ở application policy hoặc domain policy tùy ngữ nghĩa và thiết kế.

Truyền actor tường minh có một lợi ích quan trọng: chữ ký use case cho thấy thông tin nào cần để thực hiện hành động. Khi đọc code hoặc viết test, người phát triển biết dữ liệu đến từ đâu và có thể cung cấp actor giả một cách có chủ đích. Các tầng không phải tự đọc `SecurityContextHolder` ở bất kỳ vị trí nào.

Không phải mọi phương thức đều cần actor. Nếu một thao tác thuần túy không cần biết ai thực hiện, đừng thêm tham số context chỉ vì “có thể sau này cần”. Truyền đúng thông tin qua đúng ranh giới sẽ giữ hợp đồng nhỏ và dễ hiểu.

## 4. Tenant context và ranh giới dữ liệu

Trong hệ thống multi-tenant, `tenantId` thường ảnh hưởng đến quyền truy cập dữ liệu. Nó cần được xác định từ danh tính hoặc membership đã được xác minh, sau đó được truyền tới use case và tầng truy cập dữ liệu ở những thao tác cần giới hạn tenant.

Ví dụ repository có thể yêu cầu tenant trong chữ ký:

```java
public interface OrderRepository {
    Optional<Order> findByIdAndTenantId(OrderId orderId, TenantId tenantId);
}
```

Adapter phải áp dụng điều kiện tenant trong truy vấn:

```java
@Query("""
    select o from OrderJpaEntity o
    where o.id = :orderId and o.tenantId = :tenantId
    """)
Optional<OrderJpaEntity> findForTenant(
    String orderId,
    String tenantId
);
```

Đây là ví dụ rút gọn về cách đưa tenant vào điều kiện truy vấn. Việc ẩn nút hoặc lọc danh sách ở UI không phải là kiểm soát truy cập dữ liệu. Repository hoặc cơ chế persistence tương ứng cần bảo đảm một truy vấn không thể vô tình trả dữ liệu tenant khác. Với thao tác cập nhật và xóa, điều kiện tenant cũng cần được áp dụng, hoặc cần xác minh tenant của aggregate trước khi thay đổi.

Nếu tenant được suy ra từ subdomain, header hoặc đường dẫn URL, tầng trình bày có thể nhận giá trị đó nhưng phải xác minh người dùng được phép hoạt động trong tenant đã chọn. Tenant context là dữ liệu phạm vi, không tự nó chứng minh quyền truy cập.

## 5. Correlation ID cho log và giao tiếp giữa các tầng

Correlation ID giúp tìm các bản ghi liên quan đến cùng một yêu cầu hoặc quy trình. Ví dụ, một yêu cầu tạo đơn hàng có thể đi qua controller, application service, repository adapter, phát sự kiện và kích hoạt một consumer xử lý tiếp. Nếu các log ghi cùng correlation ID, người vận hành có thể lọc log theo mã này để hiểu luồng xử lý.

Một cách thường dùng trong Spring MVC là filter đọc mã từ header, kiểm tra định dạng, hoặc tạo mã mới nếu không có. Filter đặt mã vào logging context (MDC), trả mã trong response header và dọn context sau khi request kết thúc:

```java
@Component
class CorrelationIdFilter extends OncePerRequestFilter {
    static final String HEADER = "X-Correlation-ID";
    static final String MDC_KEY = "correlationId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String correlationId = resolve(request.getHeader(HEADER));
        MDC.put(MDC_KEY, correlationId);
        response.setHeader(HEADER, correlationId);
        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove(MDC_KEY);
        }
    }

    private String resolve(String supplied) {
        if (supplied != null && supplied.matches("[A-Za-z0-9._-]{1,80}")) {
            return supplied;
        }
        return UUID.randomUUID().toString();
    }
}
```

Các import và cấu hình logging được lược bỏ. Filter chỉ chấp nhận ký tự và độ dài giới hạn để tránh đưa dữ liệu tùy ý vào log hoặc header. Một hệ thống có thể luôn tạo correlation ID nội bộ thay vì giữ mã do caller cung cấp; điều quan trọng là quy định rõ độ tin cậy và phạm vi duy nhất của mã. Correlation ID do client gửi không được dùng để xác thực hoặc cấp quyền.

Với Logback, MDC key `correlationId` có thể được đưa vào pattern log, ví dụ `%X{correlationId}`. Khi filter chạy trong cùng request thread, các log từ những tầng được gọi đồng bộ có thể dùng chung giá trị này mà không cần thêm tham số vào mọi phương thức.

## 6. Correlation ID không thay thế distributed trace

Correlation ID là mã tương quan ở mức ứng dụng. Distributed tracing theo dõi quan hệ cha-con giữa các thao tác bằng trace context, thường theo chuẩn W3C Trace Context với các header như `traceparent` và `tracestate`.

| Loại mã | Phạm vi thường dùng | Mục đích |
|---|---|---|
| Request ID | Một request tới một dịch vụ | Nhận diện lần tiếp nhận cụ thể |
| Correlation ID | Một luồng nghiệp vụ hoặc nhóm thao tác liên quan | Tìm log, message và audit cùng một quy trình |
| Trace ID | Một distributed trace | Liên kết các span qua nhiều dịch vụ |
| Span ID | Một thao tác trong trace | Đo thời gian và quan hệ cha-con của thao tác |

Một request có thể có correlation ID và trace ID khác nhau. Khi hệ thống dùng OpenTelemetry hoặc agent tracing, nên để instrumentation quản lý trace context và propagation chuẩn. Không tự tạo `traceparent` tùy ý hoặc thay thế trace ID bằng correlation ID. Có thể ghi cả hai trong log nếu hệ thống quan sát hỗ trợ.

## 7. Truyền ngữ cảnh qua lời gọi dịch vụ khác

Khi application service gọi một dịch vụ HTTP bên ngoài, trace context thường được instrumentation truyền tự động nếu client đã được cấu hình. Nếu hệ thống cần correlation ID nghiệp vụ, adapter có thể đưa mã đó vào header theo hợp đồng tích hợp.

```java
class ShippingClientAdapter {
    private final WebClient webClient;
    private final CorrelationIdProvider correlationIds;

    ShippingClientAdapter(
            WebClient webClient,
            CorrelationIdProvider correlationIds) {
        this.webClient = webClient;
        this.correlationIds = correlationIds;
    }

    Mono<ShippingResult> createShipment(CreateShipmentRequest request) {
        return webClient.post()
            .uri("/shipments")
            .header("X-Correlation-ID", correlationIds.current())
            .bodyValue(request)
            .retrieve()
            .bodyToMono(ShippingResult.class);
    }
}
```

`CorrelationIdProvider` là một abstraction ở tầng tích hợp để đọc mã hiện tại theo cơ chế đã chọn. Ví dụ không minh họa cấu hình trace propagation; hãy để OpenTelemetry hoặc thư viện tương ứng xử lý `traceparent`. Không gửi access token, cookie, toàn bộ principal hoặc dữ liệu nhạy cảm trong header chỉ để “truyền context”. Nếu dịch vụ đích cần danh tính người dùng, thiết kế cơ chế ủy quyền hoặc service-to-service authentication riêng, có kiểm tra phạm vi và thời hạn.

## 8. Ngữ cảnh trong xử lý bất đồng bộ và message

Một request có thể phát message để xử lý sau. Khi đó thread của HTTP request đã kết thúc nhưng công việc phía sau vẫn cần biết sự kiện thuộc tenant nào, do actor nào khởi tạo và có correlation ID nào.

Ví dụ metadata message:

```java
public record MessageMetadata(
    String correlationId,
    String causationId,
    String actorId,
    String tenantId,
    ActorKind actorKind
) {}

public record OrderPlacedEvent(
    String orderId,
    MessageMetadata metadata
) {}
```

`correlationId` liên kết các message cùng một quy trình; `causationId` có thể chỉ ra message hoặc thao tác trực tiếp tạo ra sự kiện này. Consumer khôi phục metadata từ message đã được broker và ứng dụng xác thực, rồi dùng nó cho audit, log, tenant scoping và các quyết định được phép. Không được mặc định mọi header message là đáng tin chỉ vì chúng tồn tại; quyền publish, nguồn phát và tính toàn vẹn message cần được bảo vệ.

Trong consumer, actor ban đầu có thể chỉ là thông tin audit. Quyền thực thi công việc hiện tại thường thuộc service account của consumer. Nếu cần tiếp tục ủy quyền theo người dùng đã khởi tạo, phải có mô hình delegation rõ ràng và kiểm tra quyền phù hợp; không nên sao chép bearer token ban đầu vào message để dùng vô thời hạn.

## 9. Cẩn trọng với ThreadLocal và tác vụ song song

MDC, `SecurityContextHolder` và một số cơ chế request context thường dựa trên `ThreadLocal`. Chúng thuận tiện cho xử lý đồng bộ trên một thread, nhưng không tự động truyền sang thread khác, `@Async`, executor tùy chỉnh hoặc consumer message.

Nếu dùng thread pool, thread được tái sử dụng. Không dọn context có thể khiến log của request sau mang correlation ID hoặc security context của request trước. Luôn đặt và dọn context trong `try/finally`. Với công việc bất đồng bộ, có thể:

- Truyền một đối tượng context bất biến vào tác vụ hoặc message một cách tường minh.
- Dùng `TaskDecorator` hoặc cơ chế context propagation được framework hỗ trợ để chụp context khi submit và khôi phục/dọn context khi chạy.
- Dùng OpenTelemetry context propagation cho trace, thay vì tự sao chép các span ID.

Ví dụ ý tưởng với tác vụ bất đồng bộ:

```java
ExecutionContext context = currentContext.snapshot();
executor.execute(() -> processor.process(command, context));
```

`ExecutionContext` cần là snapshot bất biến và chỉ chứa trường cần cho tác vụ. Đừng giữ nguyên `HttpServletRequest`, session hoặc đối tượng `Authentication` trong một tác vụ chạy lâu sau khi request đã kết thúc.

Với reactive pipeline, không nên giả định MDC dựa trên thread-local sẽ luôn đúng vì một luồng có thể đổi thread. Dùng cơ chế context của Reactor và bridge tương ứng với logging/tracing stack đang dùng.

## 10. Bảo mật và quyền riêng tư khi truyền context

Context có thể chứa dữ liệu nhạy cảm. Hãy áp dụng nguyên tắc tối thiểu:

- Chỉ truyền user ID, tenant ID, locale hoặc scope thật sự cần thiết; không truyền toàn bộ token hay principal object qua mọi tầng.
- Không ghi access token, session ID, mật khẩu, thông tin thanh toán hoặc dữ liệu cá nhân nhạy cảm vào MDC hay correlation header.
- Correlation ID không phải bí mật và không phải bằng chứng xác thực. Người ngoài có thể biết hoặc tự tạo một mã hợp lệ về định dạng.
- Xác minh tenant và quyền truy cập ở phía server; không tin user ID hoặc tenant ID do client tùy ý gửi.
- Nếu có impersonation hoặc delegated access, lưu riêng actor khởi tạo và subject đang được đại diện để audit không nhập nhằng.
- Giới hạn độ dài, ký tự và thời gian lưu của metadata để tránh log injection, dữ liệu rác và lưu giữ quá mức.

Log nên trả lời ai đã làm gì, trên tài nguyên nào và kết quả ra sao, nhưng không cần ghi mọi thuộc tính của context. Hãy dùng ID nội bộ hoặc giá trị đã che/mã hóa theo chính sách dữ liệu của tổ chức.

## 11. Kiểm thử việc truyền context

Nên kiểm tra từng ranh giới thay vì chỉ kiểm tra filter:

- **Controller test:** xác minh principal đã xác thực được chuyển thành `ActorContext` đúng; giá trị user hoặc tenant giả mạo trong request không ghi đè principal.
- **Application test:** xác minh actor và tenant được chuyển đúng cho policy/repository, use case từ chối thao tác không có quyền và vẫn thực thi quy tắc miền.
- **Repository integration test:** xác minh truy vấn tenant không trả hoặc sửa dữ liệu của tenant khác.
- **Filter test:** xác minh correlation ID hợp lệ được giữ theo chính sách, mã thiếu hoặc sai định dạng được tạo mới, response header được đặt và MDC được dọn cả khi có exception.
- **Async/message test:** xác minh metadata cần thiết được ghi vào message, consumer khôi phục đúng context và không rò rỉ context giữa hai tác vụ chạy trên cùng thread.
- **Tracing test hoặc quan sát tích hợp:** xác minh trace context được truyền qua HTTP client hoặc message broker bằng instrumentation đã cấu hình.

Một test quan trọng là chạy hai tác vụ liên tiếp trên cùng executor thread với hai correlation ID khác nhau và xác minh tác vụ thứ hai không nhìn thấy ID của tác vụ thứ nhất.

## 12. Checklist thiết kế

Khi thiết kế việc truyền context qua các tầng, hãy hỏi:

1. Actor là user, service hay system? Danh tính đến từ bước xác thực nào?
2. Tenant hoặc phạm vi dữ liệu được xác minh ra sao, và tầng dữ liệu áp dụng điều kiện đó ở đâu?
3. Use case nào thực sự cần actor hoặc context? Có thể truyền tường minh bằng command/query không?
4. Correlation ID được tạo, kiểm tra, trả về và truyền tiếp theo quy tắc nào?
5. Trace ID/span ID được quản lý bằng instrumentation chuẩn nào?
6. Khi gọi HTTP, phát message hoặc chạy async, context nào cần được truyền và context nào cần được tạo mới?
7. Có cơ chế dọn ThreadLocal/MDC và khôi phục context an toàn khi dùng thread pool không?
8. Có dữ liệu nhạy cảm hoặc quyền nào đang bị truyền quá rộng hay ghi vào log không?
9. Kiểm thử đã bao phủ cả đường thành công, lỗi và tác vụ bất đồng bộ chưa?

## 13. Ghi nhớ

Định danh actor cho biết ai hoặc thành phần nào khởi tạo hành động; execution context cung cấp phạm vi như tenant; correlation ID liên kết log và message của một luồng xử lý. Hãy lấy danh tính từ nguồn đã xác thực, xác minh tenant ở phía server và truyền những thông tin use case cần qua hợp đồng có kiểu. Correlation ID có thể được đặt trong MDC để hỗ trợ log đồng bộ, nhưng phải dọn trong `finally`; với async và message, hãy truyền snapshot metadata tường minh hoặc dùng cơ chế context propagation phù hợp. Distributed trace có trace ID/span ID riêng và nên được quản lý bằng chuẩn instrumentation. Không dùng correlation ID để cấp quyền, không truyền token hoặc principal quá rộng và kiểm thử việc truyền context qua từng ranh giới.
