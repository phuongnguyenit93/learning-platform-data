# Truyền danh tính, mã theo dõi và khách thuê qua Reactor Context

Trong ứng dụng Spring WebFlux kết hợp Spring Data R2DBC, một request có thể đi qua nhiều tầng bất đồng bộ: WebFilter, controller, service, repository, WebClient và các callback xử lý kết quả. Các tầng này có thể chạy trên những thread khác nhau, nhưng vẫn cần dùng chung một số thông tin của request như người dùng đã xác thực, tenant hiện tại, correlation ID hoặc trace context.

Reactor Context cung cấp một vùng dữ liệu gắn với subscription để truyền những thông tin này xuyên suốt reactive pipeline. Nó giải quyết nhu cầu context propagation trong mô hình reactive, nơi không thể dựa mặc định vào `ThreadLocal` như trong ứng dụng imperative. Spring Security WebFlux cũng sử dụng Reactor Context để lưu `SecurityContext`; Spring Data R2DBC có thể đọc auditor từ reactive security context; ứng dụng có thể thêm tenant ID hoặc correlation ID để các tầng dưới sử dụng.

Reactor Context chỉ là cơ chế truyền dữ liệu trong pipeline. Nó không tự xác thực người dùng, không tự bảo vệ truy vấn tenant, không tự thêm trace header và cũng không tự thiết lập session của database. Mỗi thông tin vẫn cần nguồn đáng tin cậy, quy tắc kiểm tra và điểm sử dụng rõ ràng.

## 1. Vì sao reactive application cần Reactor Context?

Trong ứng dụng đồng bộ, một request thường chạy trên một thread trong phần lớn vòng đời xử lý. Một số framework dùng `ThreadLocal` để lưu security principal, MDC logging hoặc transaction metadata. Khi chuyển sang WebFlux, một request có thể tiếp tục trên thread khác sau khi I/O hoàn tất. Một thread cũng có thể lần lượt xử lý nhiều request khác nhau.

Ví dụ:

```text
Request A: Thread-1 -> Thread-4 -> Thread-2
Request B: Thread-2 -> Thread-3 -> Thread-1
```

Nếu lưu tenant ID hoặc user ID vào một `ThreadLocal` rồi đọc ở bất kỳ callback nào, code có thể không thấy giá trị hoặc đọc nhầm giá trị còn sót lại từ công việc khác nếu việc dọn dẹp không chính xác.

Reactor Context gắn với subscription thay vì thread:

```text
Request A subscription
  Context: user=1008, tenant=acme, correlation=abc...
       |
       +--> WebFilter
       +--> Controller
       +--> Service
       +--> Repository

Request B subscription
  Context: user=2042, tenant=globex, correlation=xyz...
       |
       +--> WebFilter
       +--> Controller
       +--> Service
       +--> Repository
```

Hai request có context riêng ngay cả khi các callback của chúng được thực thi trên cùng một thread ở những thời điểm khác nhau.

### 1.1. Những loại thông tin thường truyền qua Context

- **Identity:** user ID, principal hoặc actor đã được xác thực.
- **Tenant:** tenant ID đã được xác định và kiểm tra quyền.
- **Correlation ID:** mã dùng để liên kết log giữa các tầng trong cùng một request.
- **Trace context:** trace ID, span ID và thông tin sampling do hệ thống tracing quản lý.
- **Request metadata:** locale, channel hoặc một số thông tin bất biến khác có phạm vi subscription.

Không nên đưa toàn bộ request, entity lớn, connection, mutable map hoặc dữ liệu nhạy cảm không cần thiết vào Context. Context phù hợp với metadata nhỏ, ổn định và có phạm vi rõ ràng.

## 2. Reactor Context và các API cơ bản

Reactor Context là một cấu trúc key-value bất biến, gắn với subscriber. Khi thêm hoặc thay đổi giá trị, Reactor tạo một Context mới; các operator phía upstream nhìn thấy Context được cung cấp bởi subscriber ở phía downstream.

Các API thường dùng:

| API | Mục đích |
|---|---|
| `contextWrite(...)` | Ghi hoặc biến đổi Context cho phần upstream của publisher |
| `deferContextual(...)` | Đọc `ContextView` khi subscription xảy ra |
| `ContextView` | Đọc các giá trị context mà không sửa đổi |
| `Context.of(...)` | Tạo Context ban đầu với các cặp key-value |
| `contextRead()` | Đọc Context hiện tại trong một số operator nâng cao |

### 2.1. Ghi giá trị bằng contextWrite

```java
Mono<String> pipeline = Mono.deferContextual(context ->
        Mono.just("tenant=" + context.get("tenantId")))
    .contextWrite(context -> context.put("tenantId", "acme"));
```

Khi subscribe, `deferContextual` đọc được `tenantId` do `contextWrite` cung cấp. Context được ghi ở cuối pipeline nhưng có hiệu lực đối với các operator upstream của vị trí đó.

Có thể dùng overload đơn giản:

```java
Mono<String> pipeline = Mono.just("loaded")
        .contextWrite(Context.of("correlationId", "req-123"));
```

Trong code ứng dụng, nên dùng key có tên rõ ràng và hằng số thay vì chuỗi rải rác.

### 2.2. Đọc bằng deferContextual

```java
Mono<OrderView> findOrder(Long orderId) {
    return Mono.deferContextual(context -> {
        String tenantId = context.get("tenantId");
        return orderRepository.findByTenantIdAndId(tenantId, orderId)
                .map(OrderView::fromEntity);
    });
}
```

`deferContextual` trì hoãn việc đọc Context đến lúc subscribe. Không đọc Context ở thời điểm tạo publisher vì lúc đó subscription context có thể chưa được thiết lập.

Nếu key có thể không tồn tại, dùng `hasKey` hoặc `getOrEmpty` và xử lý trường hợp thiếu một cách tường minh:

```java
return Mono.deferContextual(context -> {
    if (!context.hasKey(TENANT_ID)) {
        return Mono.error(new MissingTenantContextException());
    }

    String tenantId = context.get(TENANT_ID);
    return orderRepository.findByTenantIdAndId(tenantId, orderId);
});
```

Đối với tenant-scoped data, thiếu tenant thường phải là lỗi rõ ràng. Không nên tự dùng một tenant mặc định vì có thể dẫn đến truy cập sai phạm vi dữ liệu.

### 2.3. ContextView là read-only

`ContextView` cho phép đọc key/value. Nó không cung cấp thao tác sửa context. Muốn bổ sung giá trị, dùng `contextWrite` ở vị trí phù hợp.

### 2.4. Context có phạm vi subscription

Giá trị Context chỉ có hiệu lực cho subscription được truyền vào. Hai lần subscribe vào cùng một publisher có thể dùng hai Context khác nhau:

```java
Mono<String> currentTenant = Mono.deferContextual(ctx ->
        Mono.just(ctx.get(TENANT_ID)));

Mono<String> acme = currentTenant
        .contextWrite(ctx -> ctx.put(TENANT_ID, "acme"));

Mono<String> globex = currentTenant
        .contextWrite(ctx -> ctx.put(TENANT_ID, "globex"));
```

Không lưu Context của request vào field singleton hoặc biến static để tái sử dụng giữa các request. Context thuộc subscription, không phải trạng thái dùng chung của bean.

## 3. Hiểu đúng hướng áp dụng của contextWrite

Một điểm dễ nhầm là `contextWrite` tác động theo hướng ngược với cách đọc code từ trên xuống. Nó ghi Context cho các operator ở phía upstream, tức những operator nằm trước vị trí `contextWrite` trong chuỗi publisher.

Ví dụ:

```java
Mono.deferContextual(ctx -> Mono.just(ctx.get("key")))
        .contextWrite(ctx -> ctx.put("key", "value"));
```

`deferContextual` nằm upstream của `contextWrite`, nên đọc được `value`.

Ngược lại:

```java
Mono.deferContextual(ctx -> Mono.just(ctx.getOrDefault("key", "missing")))
        .contextWrite(ctx -> ctx.put("key", "value"))
        .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("key", "missing"))));
```

Operator `flatMap` ở phía downstream của `contextWrite` không tự nhìn thấy giá trị mà `contextWrite` vừa ghi cho upstream trước đó. Context được cung cấp từ subscriber và truyền vào upstream theo vị trí operator.

Khi cần hiểu một pipeline phức tạp, hãy xác định publisher nào là upstream, operator nào đọc Context và `contextWrite` nằm ở đâu. Có thể tách pipeline thành các method nhỏ để ranh giới context dễ thấy hơn.

## 4. Định nghĩa key và kiểu dữ liệu context thống nhất

Không nên dùng các chuỗi như `"tenant"`, `"user"` hoặc `"trace"` tùy ý ở nhiều lớp. Định nghĩa key tập trung:

```java
public final class RequestContextKeys {

    public static final String CORRELATION_ID = "app.correlationId";
    public static final String TENANT_ID = "app.tenantId";
    public static final String ACTOR_ID = "app.actorId";

    private RequestContextKeys() {
    }
}
```

Có thể tạo một record để nhóm metadata đã được kiểm tra:

```java
public record RequestMetadata(
        String correlationId,
        String tenantId,
        Long actorId
) {
}
```

Sau đó lưu một object immutable duy nhất:

```java
return chain.filter(exchange)
        .contextWrite(context -> context.put(REQUEST_METADATA, metadata));
```

Kiểu object nhóm giúp tránh nhiều key rời rạc, nhưng không nên nhét mọi thứ vào một context object toàn cục. Chỉ đưa vào những trường thực sự cần được các tầng reactive downstream sử dụng.

### 4.1. Chọn kiểu key

Reactor Context cho phép key là object. Có thể dùng hằng số String có namespace hoặc một object key riêng. Dùng key object giúp tránh va chạm với thư viện khác; dùng String thuận tiện khi quan sát và tích hợp. Điều quan trọng là key phải ổn định và được quản lý tập trung.

### 4.2. Không lưu mutable object

Context bất biến không làm object bên trong tự bất biến. Nếu lưu một `HashMap` hoặc object mutable, nhiều operator có thể cùng tham chiếu và sửa nó. Ưu tiên record, immutable value object, primitive wrapper hoặc String.

## 5. Truyền correlation ID qua WebFilter

Correlation ID giúp liên kết log của một request xuyên qua WebFilter, controller, service và repository. Có thể nhận ID từ header được tin cậy hoặc tạo ID mới ở biên HTTP.

### 5.1. Tạo hoặc kiểm tra correlation ID

Ví dụ WebFilter:

```java
@Component
public class CorrelationIdWebFilter implements WebFilter {

    private static final String HEADER = "X-Correlation-Id";
    private static final String CONTEXT_KEY = "app.correlationId";

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        String supplied = exchange.getRequest()
                .getHeaders()
                .getFirst(HEADER);

        String correlationId = isSafe(supplied)
                ? supplied
                : UUID.randomUUID().toString();

        exchange.getResponse().getHeaders()
                .set(HEADER, correlationId);

        return chain.filter(exchange)
                .contextWrite(context -> context.put(CONTEXT_KEY, correlationId));
    }

    private boolean isSafe(String value) {
        return value != null
                && value.length() <= 100
                && value.matches("[A-Za-z0-9._-]+");
    }
}
```

Filter này:

1. Đọc header `X-Correlation-Id` nếu có.
2. Kiểm tra độ dài và tập ký tự được phép.
3. Tạo UUID nếu header thiếu hoặc không hợp lệ.
4. Trả ID trong response header.
5. Ghi ID vào Reactor Context cho pipeline downstream.

Nếu request đến từ proxy hoặc gateway đáng tin cậy, có thể dùng correlation ID do gateway cấp sau khi xác thực nguồn. Không mặc nhiên tin một header tùy ý từ Internet nếu hệ thống dùng ID đó để liên kết sự kiện hoặc truy cập log nhạy cảm.

### 5.2. Đọc correlation ID trong service

```java
public Mono<OrderView> getOrder(Long id) {
    return Mono.deferContextual(context -> {
        String correlationId = context.get(CORRELATION_ID);
        log.debug("Loading order id={}, correlationId={}", id, correlationId);

        return orderRepository.findById(id)
                .map(OrderView::fromEntity);
    });
}
```

Nếu service có thể được gọi ngoài HTTP, chẳng hạn từ scheduler hoặc message consumer, key có thể không tồn tại. Khi đó hãy dùng `getOrEmpty`/`hasKey` hoặc yêu cầu caller thiết lập metadata theo hợp đồng của service. Không giả định mọi subscription đều bắt nguồn từ WebFilter.

### 5.3. Không dùng correlation ID thay trace ID

Correlation ID là mã ứng dụng tự quản lý để liên kết log hoặc request. Trace ID thuộc hệ thống distributed tracing, có span, parent-child relationship và sampling. Một request có thể có correlation ID riêng trong khi nhiều service cùng tham gia một trace.

Nếu đã dùng Micrometer Tracing hoặc OpenTelemetry instrumentation, để hệ thống tracing quản lý trace/span context và truyền trace headers theo chuẩn. Có thể ghi correlation ID song song để phục vụ nghiệp vụ, nhưng không tự tạo `traceId` giả rồi ghi đè trace context do tracing framework quản lý.

## 6. Danh tính người dùng và Spring Security WebFlux

Spring Security WebFlux lưu `SecurityContext` trong Reactor Context. Ứng dụng nên đọc danh tính qua `ReactiveSecurityContextHolder` thay vì lấy từ `SecurityContextHolder` kiểu ThreadLocal.

### 6.1. Đọc Authentication trong service

```java
public Mono<CustomerProfile> currentProfile() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .filter(authentication ->
                    !(authentication instanceof AnonymousAuthenticationToken))
            .map(Authentication::getPrincipal)
            .filter(AppPrincipal.class::isInstance)
            .cast(AppPrincipal.class)
            .flatMap(principal -> customerRepository
                    .findById(principal.userId())
                    .map(CustomerProfile::fromEntity));
}
```

Ví dụ giả định ứng dụng có principal riêng:

```java
public record AppPrincipal(
        Long userId,
        String username,
        String tenantId
) {
}
```

Principal thực tế có thể là `UserDetails`, JWT principal hoặc kiểu tùy chỉnh. Hãy chuyển đổi từ kiểu được security configuration xác thực, không ép kiểu mù quáng.

### 6.2. Phân biệt authenticated và anonymous

Một số `Authentication` đại diện anonymous user vẫn có thể trả `isAuthenticated() == true`. Nếu endpoint yêu cầu người dùng thật, cần loại `AnonymousAuthenticationToken` hoặc kiểm tra principal theo chính sách bảo mật. Không chỉ dựa vào `isAuthenticated()`.

### 6.3. Không sao chép security context một cách tùy tiện

Spring Security đã quản lý `SecurityContext` qua Reactor Context. Thông thường, đọc nó bằng `ReactiveSecurityContextHolder` là đủ. Nếu muốn đưa actor ID vào một request metadata object riêng, chỉ làm sau khi xác thực và chuyển sang giá trị tối thiểu cần dùng.

Không tạo một key `userId` từ header request rồi xem nó là danh tính đã xác thực. Header hoặc body có thể bị client sửa. Danh tính phải đến từ authentication đã được Spring Security xác minh.

## 7. Truyền tenant identity an toàn

Trong multi-tenant application, tenant ID xác định phạm vi dữ liệu mà request được phép truy cập. Việc truyền tenant qua Context giúp các tầng dưới lấy được cùng một tenant, nhưng Context không phải cơ chế authorization. Giá trị tenant phải được xác định từ danh tính hoặc một cơ chế định tuyến đã xác thực và được kiểm tra quyền trước khi truy vấn.

### 7.1. Lấy tenant từ authenticated principal

```java
public Mono<OrderView> findOrder(Long orderId) {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getPrincipal)
            .cast(AppPrincipal.class)
            .flatMap(principal -> orderQueryService.findForTenant(
                    principal.tenantId(), orderId));
}
```

Đây là cách truyền tenant tường minh qua tham số method. Với code nhỏ, truyền tham số có thể rõ ràng và dễ kiểm tra hơn việc đưa mọi giá trị vào Context.

### 7.2. Ghi tenant vào Context khi nhiều tầng cần dùng

Nếu nhiều service downstream cần cùng tenant và không muốn truyền tham số qua nhiều chữ ký, có thể ghi tenant vào Context sau khi đã lấy từ principal:

```java
public Mono<OrderView> findOrder(Long orderId) {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getPrincipal)
            .cast(AppPrincipal.class)
            .flatMap(principal -> orderQueryService.find(orderId)
                    .contextWrite(context -> context.put(
                            TENANT_ID, principal.tenantId())));
}
```

`contextWrite` ở inner publisher cung cấp tenant cho các operator upstream bên trong `orderQueryService.find(...)`. Phương thức query service có thể đọc:

```java
public Mono<OrderView> find(Long orderId) {
    return Mono.deferContextual(context -> {
        String tenantId = context.get(TENANT_ID);
        return orderRepository.findByTenantIdAndId(tenantId, orderId)
                .map(OrderView::fromEntity);
    });
}
```

Đảm bảo không có đường gọi nào vào `find` mà thiếu tenant. Nếu service được gọi từ nhiều nguồn, có thể dùng API bắt buộc tenant tường minh hoặc kiểm tra Context và phát lỗi khi thiếu.

### 7.3. Không tin tenant header nếu chưa kiểm tra

Một client có thể gửi `X-Tenant-Id: other-company`. Nếu hệ thống lấy header này rồi truy vấn dữ liệu mà không kiểm tra membership/permission, đây là lỗi phân quyền xuyên tenant.

Nếu header dùng để chọn tenant trong số tenant mà user được phép truy cập, cần:

1. Xác thực user.
2. Đọc tenant được yêu cầu.
3. Kiểm tra user có quyền truy cập tenant đó.
4. Chỉ sau khi kiểm tra thành công mới ghi tenant vào Context hoặc truyền vào query.

Nếu user chỉ có một tenant cố định, lấy tenant từ principal hoặc claim đã được xác thực thường đơn giản hơn.

### 7.4. Tenant phải xuất hiện trong điều kiện truy vấn

Reactor Context không tự thêm `WHERE tenant_id = ...`. Repository/query vẫn phải ràng buộc tenant:

```java
Flux<OrderEntity> findByTenantIdAndStatus(
        String tenantId, String status);
```

Hoặc với SQL:

```sql
SELECT id, order_code, status
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
```

Không dùng `findById(id)` cho dữ liệu tenant-scoped nếu chỉ có ID không đủ để xác định quyền truy cập. Có thể dùng `findByTenantIdAndId(tenantId, id)` để ràng buộc ngay tại database.

## 8. Tích hợp tenant với PostgreSQL Row-Level Security

Một số hệ thống dùng Row-Level Security (RLS) để database áp dụng policy theo tenant. Trong PostgreSQL, ứng dụng có thể đặt tenant vào transaction-local setting rồi policy đọc setting đó.

Ví dụ policy minh họa:

```sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON orders
USING (tenant_id = current_setting('app.tenant_id', true));
```

Trong một transaction, có thể đặt tenant bằng:

```sql
SELECT set_config('app.tenant_id', :tenantId, true);
```

Tham số thứ ba `true` yêu cầu setting có phạm vi transaction-local trong PostgreSQL. Điều này quan trọng khi connection được tái sử dụng qua pool.

### 8.1. Thiết lập setting trong cùng transaction

Ví dụ thể hiện việc đọc hàng kết quả của `SELECT set_config`:

```java
@Transactional(readOnly = true)
public Flux<OrderEntity> findOrdersForTenant(String tenantId) {
    return databaseClient.sql(
                    "SELECT set_config('app.tenant_id', :tenantId, true)")
            .bind("tenantId", tenantId)
            .map((row, metadata) -> row.get(0, String.class))
            .one()
            .thenMany(orderRepository.findAll());
}
```

Đối với ứng dụng thật, tenant nên đến từ context đã xác thực, không phải tham số tùy ý từ controller. Có thể đọc tenant từ Reactor Context bên trong method rồi thực hiện transaction tương ứng.

### 8.2. Tránh session state rò rỉ qua connection pool

Không đặt tenant bằng `SET app.tenant_id = ...` ở session scope rồi trả connection về pool mà không reset. Connection tiếp theo có thể được cấp cho request tenant khác và kế thừa session setting cũ.

Transaction-local setting cùng transaction boundary giúp giảm nguy cơ rò rỉ state. Tuy nhiên, cần test rollback/commit và xác nhận driver/pool trả connection về trạng thái sạch. RLS là lớp bảo vệ bổ sung; vẫn cần authorization ở ứng dụng và kiểm tra policy không cho phép tenant context giả mạo.

## 9. Truyền correlation ID và tenant sang WebClient

Khi Service gọi một downstream HTTP service, correlation ID có thể được truyền trong header để liên kết log giữa các dịch vụ. Có thể đọc Context ngay trong pipeline:

```java
public Mono<ProductInfo> loadProduct(String productCode) {
    return Mono.deferContextual(context ->
            webClient.get()
                    .uri("/products/{code}", productCode)
                    .header("X-Correlation-Id",
                            context.getOrDefault(CORRELATION_ID, "unknown"))
                    .retrieve()
                    .bodyToMono(ProductInfo.class));
}
```

Không gửi tenant hoặc user ID tới dịch vụ khác nếu hợp đồng và chính sách bảo mật không yêu cầu. Nếu cần, gửi một claim/token được xác thực hoặc dùng cơ chế service-to-service identity thích hợp. Không xem header correlation ID là bằng chứng xác thực.

### 9.1. Dùng filter cho WebClient

Nếu nhiều request cần cùng logic thêm correlation header, có thể viết `ExchangeFilterFunction` hoặc cấu hình observation/tracing instrumentation. Tuy nhiên, filter cần đọc Context ở đúng thời điểm subscription và không giữ metadata của request trước trong singleton field.

### 9.2. Distributed tracing

Với Micrometer Tracing/OpenTelemetry, instrumentation thường tự truyền trace context qua WebClient và các transport được hỗ trợ. Dùng tracing bridge và observation instrumentation tương ứng với phiên bản Spring Boot. Tránh tự đặt `traceparent` bằng một chuỗi correlation ID vì traceparent có định dạng và semantics riêng.

## 10. Logging và MDC

Nhiều logging framework dùng MDC dựa trên `ThreadLocal`. Reactor Context không tự động đồng bộ mọi giá trị sang MDC trong tất cả phiên bản và cấu hình.

### 10.1. Đọc Context để ghi log trong pipeline

Có thể dùng `deferContextual` hoặc `doOnEach` để lấy metadata tại signal:

```java
return Mono.deferContextual(context -> {
    String correlationId = context.getOrDefault(CORRELATION_ID, "-");
    log.info("Processing order, correlationId={}", correlationId);
    return orderRepository.findById(orderId);
});
```

Cách này tường minh và không phụ thuộc MDC. Nếu muốn correlation ID tự xuất hiện trong mọi log line, cần cấu hình context propagation/MDC bridge.

### 10.2. Micrometer Context Propagation

Spring ecosystem có thể tích hợp Micrometer Context Propagation để capture/restore một số `ThreadLocal` values khi chuyển giữa reactive và imperative code. Với Reactor, automatic context propagation có thể được bật bằng hook phù hợp trong phiên bản thư viện đang dùng, ví dụ `Hooks.enableAutomaticContextPropagation()`.

Chỉ bật khi đã hiểu tác động và có cấu hình `ThreadLocalAccessor` tương ứng. Không giả định mọi MDC key hoặc thư viện logging được tự động propagate chỉ vì đã thêm dependency. Kiểm tra hướng dẫn của Spring Boot/Micrometer theo phiên bản dự án.

### 10.3. Không tự quản lý MDC thiếu cleanup

Nếu tự đặt MDC trong callback, phải xóa hoặc khôi phục giá trị trong mọi đường kết thúc, bao gồm complete, error và cancel. Thread được tái sử dụng; nếu không cleanup, log của request sau có thể mang correlation ID của request trước.

Với ứng dụng mới, ưu tiên Micrometer Tracing/Context Propagation được cấu hình đúng hoặc log metadata tường minh từ Context thay vì tự viết bridge ThreadLocal rải rác.

## 11. Reactor Context và R2DBC auditing

Spring Data auditing trong R2DBC sử dụng `ReactiveAuditorAware<T>` để lấy actor hiện tại. Nếu ứng dụng dùng Spring Security WebFlux, provider có thể đọc principal từ `ReactiveSecurityContextHolder`, vốn dựa trên Reactor Context.

Ví dụ:

```java
@Bean
ReactiveAuditorAware<Long> auditorProvider() {
    return () -> ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .filter(authentication ->
                    !(authentication instanceof AnonymousAuthenticationToken))
            .map(Authentication::getPrincipal)
            .cast(AppPrincipal.class)
            .map(AppPrincipal::userId);
}
```

Với entity:

```java
@Table("orders")
public record OrderEntity(
        @Id Long id,
        String orderCode,
        @CreatedBy @Column("created_by") Long createdBy,
        @LastModifiedBy @Column("last_modified_by") Long lastModifiedBy
) {
}
```

Khi auditing được bật bằng `@EnableR2dbcAuditing`, callback có thể lấy auditor trong reactive context lúc lưu entity. Không cần tự đọc user ID rồi gán vào mọi entity nếu cơ chế auditing đã được cấu hình đúng.

### 11.1. Tác vụ nền không có SecurityContext

Scheduler, message consumer hoặc batch job có thể chạy ngoài HTTP security chain. `ReactiveSecurityContextHolder.getContext()` khi đó có thể hoàn tất rỗng. Quy định chính sách riêng:

- Cho phép auditor null nếu schema và nghiệp vụ chấp nhận.
- Gán system actor trong đúng luồng tác vụ nền.
- Yêu cầu một actor service được xác thực nếu job đại diện cho một hệ thống khác.

Không đặt một system user mặc định cho mọi request thiếu security context, vì như vậy request không xác thực có thể được ghi nhận như công việc hệ thống hợp lệ.

## 12. Context propagation qua operator và scheduler

Reactor Context được thiết kế để hoạt động qua các operator Reactor thông thường. Việc chuyển scheduler bằng `publishOn` hoặc `subscribeOn` không tự làm mất Context của subscription:

```java
Mono.deferContextual(context ->
        Mono.just(context.get(CORRELATION_ID)))
    .publishOn(Schedulers.parallel())
    .contextWrite(context -> context.put(CORRELATION_ID, "req-123"));
```

Tuy nhiên, Context không tự đi theo mọi cơ chế thực thi bên ngoài Reactor.

### 12.1. Nested subscribe làm đứt pipeline

Không nên gọi `subscribe()` bên trong Service:

```java
public Mono<Void> process(Long id) {
    repository.findById(id)
            .doOnNext(entity -> auditService.write(entity).subscribe())
            .then();
    return Mono.empty();
}
```

Subscription lồng nhau không còn nằm trong pipeline mà caller kiểm soát. Context, transaction, cancellation và error handling có thể không được truyền như mong đợi.

Hãy nối publisher bằng `flatMap` hoặc `then`:

```java
public Mono<Void> process(Long id) {
    return repository.findById(id)
            .flatMap(auditService::write)
            .then();
}
```

### 12.2. Tạo thread hoặc executor thủ công

Nếu code gọi `new Thread`, `ExecutorService.submit` hoặc callback của thư viện không tích hợp Reactor, Context không tự xuất hiện trong luồng đó. Dùng scheduler/adapter có hỗ trợ context propagation hoặc truyền metadata tường minh qua tham số.

### 12.3. Callback imperative

Khi gọi thư viện imperative cần `ThreadLocal`, cần bridge context có chủ đích. Micrometer Context Propagation cung cấp abstraction để capture và restore context; việc cấu hình phụ thuộc thư viện và phiên bản. Đừng dựa vào việc thread hiện tại tình cờ giống thread trước đó.

## 13. Context trong message consumer và tác vụ nền

Không phải mọi subscription đều bắt nguồn từ HTTP. Kafka/RabbitMQ consumer, scheduler và batch job cũng có thể cần correlation ID, tenant hoặc actor.

Ví dụ khi xử lý một message có metadata đã được xác thực:

```java
Mono<Void> handle(OrderCreatedMessage message) {
    return orderProcessor.process(message)
            .contextWrite(context -> context
                    .put(CORRELATION_ID, message.correlationId())
                    .put(TENANT_ID, message.tenantId())
                    .put(ACTOR_ID, SYSTEM_ACTOR_ID));
}
```

Đoạn code giả định message đến từ nguồn tin cậy và consumer đã xác minh tenant/actor theo hợp đồng. Không tin tenant ID chỉ vì nó có mặt trong payload message; message broker cũng cần authentication, authorization và kiểm tra producer.

Với scheduled job, có thể tạo correlation ID mới cho mỗi lần chạy hoặc dùng execution ID ổn định. Ghi Context ở ranh giới bắt đầu subscription để mọi publisher downstream dùng chung metadata.

## 14. Context và transaction R2DBC

Spring quản lý reactive transaction thông qua Reactor Context. Transactional operator hoặc `@Transactional` thiết lập transaction context cho publisher được quản lý; các thao tác R2DBC downstream tham gia transaction khi dùng đúng transaction manager và cùng pipeline.

Điều này có nghĩa Context có thể mang cả metadata ứng dụng lẫn transaction state do framework quản lý. Không sửa hoặc ghi đè key nội bộ của Spring/Reactor. Dùng namespace riêng cho key ứng dụng.

Ví dụ:

```java
@Transactional
public Mono<OrderEntity> createOrder(OrderEntity order) {
    return inventoryRepository.reserve(order)
            .then(orderRepository.save(order));
}
```

Khi caller thêm correlation hoặc tenant context:

```java
return orderService.createOrder(order)
        .contextWrite(context -> context
                .put(CORRELATION_ID, correlationId)
                .put(TENANT_ID, tenantId));
```

Các thao tác trong pipeline transactional có thể đọc metadata và tham gia cùng transaction context. Tuy nhiên, tenant context không tự cấu hình database session hoặc RLS; ứng dụng vẫn phải thêm điều kiện truy vấn hoặc thiết lập transaction-local database setting như phần trước.

### 14.1. Không tự subscribe trong transaction

Nếu tạo subscription mới bằng `subscribe()` hoặc gọi `block()`, thao tác có thể chạy ngoài transaction context của publisher gốc. Luôn trả và kết hợp publisher để transaction manager điều khiển lifecycle.

### 14.2. Không giữ transaction qua công việc ngoài database

Context có thể tiếp tục tồn tại trong toàn pipeline, nhưng transaction không nên kéo dài qua HTTP call, chờ message hoặc xử lý CPU dài. Connection bị giữ lâu sẽ làm giảm khả năng phục vụ request khác.

## 15. Bảo mật và quyền riêng tư khi dùng Context

Context là metadata nội bộ của subscription, nhưng không tự làm giá trị bên trong an toàn. Hãy áp dụng các nguyên tắc:

- Chỉ ghi user/tenant sau khi xác thực và authorization.
- Không dùng header tùy ý làm actor ID hoặc tenant ID đã tin cậy.
- Không ghi token, password, session secret hoặc toàn bộ credential vào Context.
- Không log nguyên Context; nó có thể chứa thông tin nội bộ hoặc dữ liệu nhạy cảm.
- Không chia sẻ mutable object giữa request.
- Không đưa tenant context vào static field hoặc singleton state.
- Kiểm tra tenant ở query hoặc database policy, không chỉ dựa vào việc Context có giá trị.
- Dùng correlation ID để theo dõi, không dùng nó làm token xác thực.

Nếu một method bắt buộc tenant nhưng Context thiếu, fail closed bằng lỗi rõ ràng. Không fallback sang tenant mặc định hoặc bỏ điều kiện tenant.

## 16. Kiểm thử Reactor Context

Context là một phần hành vi của reactive pipeline, nên test cần subscribe publisher với Context phù hợp và xác nhận operator downstream/upstream đọc đúng giá trị.

### 16.1. Kiểm thử contextWrite và deferContextual

```java
@Test
void readsTenantFromContext() {
    Mono<String> tenant = Mono.deferContextual(context ->
            Mono.just(context.get(TENANT_ID)));

    StepVerifier.create(tenant.contextWrite(context ->
                    context.put(TENANT_ID, "acme")))
            .expectNext("acme")
            .verifyComplete();
}
```

### 16.2. Kiểm thử hai subscription không rò tenant

```java
Mono<String> tenant = Mono.deferContextual(context ->
        Mono.just(context.get(TENANT_ID)));

StepVerifier.create(tenant.contextWrite(ctx -> ctx.put(TENANT_ID, "acme")))
        .expectNext("acme")
        .verifyComplete();

StepVerifier.create(tenant.contextWrite(ctx -> ctx.put(TENANT_ID, "globex")))
        .expectNext("globex")
        .verifyComplete();
```

Test xác nhận mỗi subscription có context riêng. Với service tenant-scoped, nên kiểm tra repository nhận đúng tenant cho từng request giả lập.

### 16.3. Kiểm thử thiếu tenant

```java
StepVerifier.create(orderQueryService.find(10L))
        .expectError(MissingTenantContextException.class)
        .verify();
```

Đây là test quan trọng để bảo đảm hệ thống không âm thầm truy vấn không có tenant predicate.

### 16.4. Kiểm thử Spring Security Context

Có thể tạo `SecurityContext` giả và gắn vào pipeline bằng `ReactiveSecurityContextHolder.withSecurityContext(...)`. Xác nhận auditor hoặc service đọc đúng principal, đồng thời test trường hợp anonymous/empty context.

```java
StepVerifier.create(ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication)))
        .expectNext("alice")
        .verifyComplete();
```

### 16.5. Kiểm thử WebFilter

Dùng `WebTestClient` để xác nhận:

- Request không có correlation header nhận ID mới.
- Request có header hợp lệ giữ ID theo chính sách.
- Header không hợp lệ được thay bằng ID mới.
- Response trả correlation header.
- Service downstream đọc được cùng ID trong Reactor Context.

### 16.6. Kiểm thử context qua WebClient và transaction

Với downstream HTTP, kiểm tra correlation header được gửi đúng và tracing instrumentation tạo trace headers theo cấu hình. Với R2DBC, integration test cần xác nhận tenant predicate hoặc RLS setting thực sự áp dụng trên cùng transaction/connection, không chỉ kiểm tra Context có key.

## 17. Lỗi thường gặp

### Dùng ThreadLocal để lưu request metadata

Thread có thể đổi trong reactive pipeline. Dùng Reactor Context hoặc cơ chế context propagation được cấu hình đúng.

### Đọc Context trước khi subscribe

Context thuộc subscription. Dùng `deferContextual` để đọc đúng thời điểm.

### Đặt contextWrite sai vị trí

`contextWrite` cung cấp Context cho các operator upstream. Kiểm tra hướng pipeline và tách method nếu cần.

### Nghĩ contextWrite truyền dữ liệu xuống phía sau

Context được subscriber cung cấp và đọc ở upstream. Đừng hiểu nó như một biến được gán rồi mọi lệnh phía sau đều nhìn thấy theo thứ tự imperative.

### Dùng Context thay cho authorization

Có tenant ID trong Context không chứng minh user có quyền truy cập tenant đó. Phải xác thực và kiểm tra quyền trước khi ghi.

### Tin tenant header hoặc message payload

Header/message có thể bị giả mạo nếu không có cơ chế tin cậy. Xác minh membership và quyền trước khi sử dụng.

### Gọi subscribe lồng nhau

Subscription mới có thể mất context, transaction, cancellation và error propagation. Kết hợp publisher bằng `flatMap`, `then` hoặc operator phù hợp.

### Nghĩ publishOn làm mất Reactor Context

Các operator Reactor thông thường giữ subscription Context qua scheduler switch. Vấn đề thường xuất hiện khi đi ra ngoài Reactor hoặc tương tác với ThreadLocal không được bridge.

### Nghĩ MDC tự động nhận mọi giá trị Context

MDC dựa trên ThreadLocal. Cần Micrometer Context Propagation/tracing instrumentation hoặc bridge có cleanup rõ ràng.

### Tự đặt trace ID thay tracing framework

Correlation ID và distributed trace ID có semantics khác nhau. Để Micrometer Tracing/OpenTelemetry quản lý trace/span và propagation.

### Cho rằng Context tự thêm tenant predicate hoặc RLS

Context chỉ cung cấp dữ liệu cho code. Query phải dùng tenant ID hoặc transaction phải thiết lập RLS setting đúng cách.

### Để session tenant state rò qua pool

Không dùng session-level `SET` mà không reset. Ưu tiên transaction-local setting và test việc trả connection về pool.

## 18. Quy trình triển khai

1. Liệt kê metadata cần truyền: actor, tenant, correlation ID và trace context.
2. Xác định nguồn đáng tin cậy của từng giá trị.
3. Để Spring Security quản lý `SecurityContext` trong Reactor Context; đọc qua `ReactiveSecurityContextHolder`.
4. Tạo correlation ID tại biên HTTP hoặc gateway đáng tin cậy và ghi bằng `contextWrite` trong WebFilter.
5. Xác thực tenant selection và quyền truy cập trước khi đưa tenant vào Context.
6. Định nghĩa key tập trung hoặc một immutable request metadata record.
7. Dùng `deferContextual` tại tầng cần đọc metadata; kiểm tra key thiếu một cách tường minh.
8. Bảo đảm mọi query tenant-scoped có predicate tenant hoặc cơ chế database policy tương ứng.
9. Để Micrometer Tracing/OpenTelemetry propagate trace context và cấu hình WebClient instrumentation.
10. Dùng Micrometer Context Propagation nếu cần bridge sang ThreadLocal/MDC.
11. Không tạo nested subscription; giữ các thao tác trong cùng reactive pipeline và transaction khi cần.
12. Tạo context riêng cho message consumer/scheduler với actor và correlation ID phù hợp.
13. Kiểm thử hai subscription song song để xác nhận không rò tenant/user/correlation ID.
14. Kiểm thử thiếu context, anonymous user, tenant không được phép và cancellation.

## 19. Checklist ghi nhớ

- [ ] Dùng Reactor Context cho metadata có phạm vi subscription, không dùng ThreadLocal trực tiếp.
- [ ] Dùng `contextWrite` để thêm giá trị và `deferContextual` để đọc khi subscribe.
- [ ] Hiểu `contextWrite` cung cấp Context cho operator upstream.
- [ ] Dùng key thống nhất và giá trị immutable, nhỏ gọn.
- [ ] Đọc danh tính qua `ReactiveSecurityContextHolder` trong WebFlux.
- [ ] Không tin user ID hoặc tenant ID tùy ý từ header/body.
- [ ] Kiểm tra quyền truy cập tenant trước khi ghi tenant vào Context.
- [ ] Query tenant-scoped luôn có tenant predicate hoặc RLS policy được xác nhận.
- [ ] Correlation ID không bị nhầm với trace ID.
- [ ] Để tracing instrumentation quản lý trace/span propagation.
- [ ] Cấu hình MDC/ThreadLocal bridge có chủ đích và cleanup đúng.
- [ ] Không gọi `subscribe()` hoặc `block()` bên trong Service để tạo luồng rời.
- [ ] Giữ R2DBC transaction trong cùng reactive pipeline.
- [ ] Tenant session setting không rò qua connection pool.
- [ ] Message consumer và scheduler thiết lập context theo nguồn tin cậy riêng.
- [ ] Có test cho context propagation, context isolation, thiếu key và tenant authorization.

Reactor Context là nền tảng để truyền metadata theo subscription trong WebFlux và Spring Data R2DBC. Khi danh tính được lấy từ Spring Security, tenant được xác thực trước khi sử dụng, correlation ID được tạo tại biên request và trace context do instrumentation quản lý, các tầng reactive có thể phối hợp mà không phụ thuộc vào thread cố định. Context chỉ cung cấp thông tin cho pipeline; truy vấn, transaction, authorization và database policy vẫn phải thực hiện đúng trách nhiệm của chúng.
