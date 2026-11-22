# Định tuyến kết nối dựa trên Reactor Context

## 1. Bài toán nhiều cơ sở dữ liệu

Một ứng dụng Spring Data R2DBC có thể cần truy cập nhiều database. Một số tình huống thường gặp:

- Mỗi tenant có một database riêng.
- Dữ liệu được chia theo vùng hoặc khách hàng.
- Ứng dụng cần chuyển đổi giữa database đọc và database ghi.
- Các nhóm dữ liệu được lưu ở những database độc lập.
- Môi trường hoặc khách hàng có cấu hình kết nối khác nhau.

Nếu mọi repository đều dùng một `ConnectionFactory`, các thao tác sẽ đi tới cùng một đích. Khi cần chọn database theo tenant hoặc ngữ cảnh của request, ứng dụng cần một lớp định tuyến connection.

Trong lập trình imperative, một cách cũ thường gặp là lưu route key trong `ThreadLocal`. Cách đó không phù hợp với reactive pipeline vì một request có thể chuyển qua nhiều thread. Với Spring Data R2DBC, route key nên được truyền qua **Reactor Context** và được đọc tại thời điểm lấy connection.

Ý tưởng là tạo một `ConnectionFactory` định tuyến, bên dưới có nhiều `ConnectionFactory` đích. Khi repository cần connection, routing factory đọc route key từ Reactor Context rồi chọn factory tương ứng.

## 2. Reactor Context là gì?

Reactor Context là vùng dữ liệu gắn với một subscription reactive. Nó cho phép truyền metadata xuyên suốt pipeline mà không phụ thuộc thread đang chạy callback.

Ví dụ, ứng dụng có thể đặt tenant key vào context:

```java
Mono<Customer> result = customerRepository.findById(customerId)
        .contextWrite(context -> context.put("tenant-route", "tenant-a"));
```

`contextWrite` tạo context chứa key `tenant-route` cho phần upstream của pipeline. Khi một publisher upstream cần lấy connection, routing factory có thể đọc giá trị này.

Đặc điểm quan trọng:

- Context thuộc subscription, không thuộc một thread cố định.
- Reactor Context là immutable; các toán tử tạo context mới thay vì sửa object context cũ.
- `contextWrite` ảnh hưởng tới các toán tử upstream của vị trí nó được đặt.
- Các toán tử Reactor thông thường duy trì context khi chuyển thread.
- Một subscription mới tạo bằng `subscribe()` không tự động chia sẻ context của subscription khác.

Vì route key phải có mặt trước khi connection được lấy, hãy đặt context ở ranh giới ngoài của publisher hoặc request pipeline, trước khi các thao tác R2DBC bắt đầu.

## 3. Vì sao không dùng ThreadLocal để định tuyến?

Một thread trong ứng dụng reactive có thể phục vụ nhiều request theo các thời điểm khác nhau. Một request cũng có thể bắt đầu trên thread này rồi tiếp tục trên thread khác do scheduler hoặc driver.

Ví dụ sau không an toàn trong reactive code:

```java
TenantContextHolder.setCurrentTenant("tenant-a");
return customerRepository.findAll();
```

Nếu `TenantContextHolder` dùng `ThreadLocal`, việc lấy route key có thể diễn ra trên thread khác với thread đã đặt giá trị. Ngược lại, một thread được tái sử dụng có thể còn giữ giá trị của request trước nếu không được dọn đúng cách.

Reactor Context giải quyết vấn đề bằng cách gắn route key với subscription:

```java
return customerRepository.findAll()
        .contextWrite(context -> context.put(
                TenantRouteContext.ROUTE_KEY,
                "tenant-a"));
```

Khi pipeline chuyển thread, context vẫn được truyền theo subscription. Không cần tự copy tenant key qua `ThreadLocal`.

## 4. ConnectionFactory định tuyến

R2DBC định nghĩa `ConnectionFactory` là abstraction tạo connection. Spring Framework cung cấp `AbstractRoutingConnectionFactory` để chọn một trong nhiều `ConnectionFactory` đích dựa trên lookup key.

Lớp này nằm trong package:

```java
org.springframework.r2dbc.connection.lookup.AbstractRoutingConnectionFactory
```

Ứng dụng kế thừa lớp đó và triển khai `determineCurrentLookupKey()`. Với R2DBC, phương thức trả về `Mono<Object>`, vì việc xác định route key có thể cần thực hiện theo reactive context.

Luồng định tuyến khái quát:

```mermaid
flowchart TD
    A[Repository / DatabaseClient] --> B[Routing ConnectionFactory]
    B --> C[Đọc route key từ Reactor Context]
    C --> D{Route key}
    D -->|tenant-a| E[ConnectionFactory A]
    D -->|tenant-b| F[ConnectionFactory B]
    D -->|Không hợp lệ| G[Lỗi định tuyến]
    E --> H[Database A]
    F --> I[Database B]
```

Routing factory không cần biết SQL nào đang chạy. Nó chỉ quyết định connection nào được dùng khi caller yêu cầu connection.

## 5. Khai báo route key dùng chung

Nên tập trung tên key vào một class để tránh gõ sai ở nhiều nơi:

```java
public final class TenantRouteContext {

    public static final String ROUTE_KEY = "tenant-route";

    private TenantRouteContext() {
    }
}
```

Route key có thể là String, enum hoặc một kiểu định danh nội bộ. Ví dụ dùng String để dễ đọc; với hệ thống lớn, enum có thể giúp tránh giá trị không hợp lệ.

Không đặt password, connection URL hoặc thông tin nhạy cảm vào Reactor Context. Context chỉ nên mang định danh route đã được xác thực; routing factory ánh xạ định danh đó tới các `ConnectionFactory` đã cấu hình.

## 6. Triển khai TenantRoutingConnectionFactory

Một implementation đơn giản đọc key từ Reactor Context:

```java
import org.springframework.r2dbc.connection.lookup.AbstractRoutingConnectionFactory;
import reactor.core.publisher.Mono;

public final class TenantRoutingConnectionFactory
        extends AbstractRoutingConnectionFactory {

    @Override
    protected Mono<Object> determineCurrentLookupKey() {
        return Mono.deferContextual(contextView ->
                Mono.justOrEmpty(
                        contextView.getOrEmpty(TenantRouteContext.ROUTE_KEY)));
    }
}
```

`Mono.deferContextual` trì hoãn việc đọc context tới lúc publisher được subscribe. `getOrEmpty` trả về giá trị nếu key có mặt, hoặc `Optional.empty()` nếu không có.

Khi key tồn tại, `AbstractRoutingConnectionFactory` dùng nó để tìm factory tương ứng trong map target. Khi key không tồn tại hoặc không khớp, hành vi phụ thuộc default target và cấu hình fallback.

Với hệ thống multi-tenant, thường nên fail closed nếu thiếu hoặc sai route key. Nếu mặc định mọi request đều chuyển về database tenant A, một request thiếu context có thể đọc/ghi nhầm dữ liệu tenant A.

## 7. Cấu hình nhiều ConnectionFactory đích

Giả sử ứng dụng có hai database PostgreSQL, một cho `tenant-a` và một cho `tenant-b`. Trước hết, cấu hình hai `ConnectionFactory` độc lập. Có thể tạo chúng bằng R2DBC driver hoặc dùng cấu hình riêng của ứng dụng.

Ví dụ phần khai báo routing factory, giả định hai bean connection factory đã được cấu hình:

```java
@Configuration
public class MultiDatabaseConfiguration {

    @Bean("tenantAConnectionFactory")
    ConnectionFactory tenantAConnectionFactory() {
        return ConnectionFactories.get(
                "r2dbc:postgresql://app:secret@localhost:5432/tenant_a");
    }

    @Bean("tenantBConnectionFactory")
    ConnectionFactory tenantBConnectionFactory() {
        return ConnectionFactories.get(
                "r2dbc:postgresql://app:secret@localhost:5432/tenant_b");
    }

    @Bean("routingConnectionFactory")
    @Primary
    ConnectionFactory routingConnectionFactory(
            @Qualifier("tenantAConnectionFactory") ConnectionFactory tenantA,
            @Qualifier("tenantBConnectionFactory") ConnectionFactory tenantB) {

        TenantRoutingConnectionFactory routing =
                new TenantRoutingConnectionFactory();

        Map<Object, ConnectionFactory> targets = new HashMap<>();
        targets.put("tenant-a", tenantA);
        targets.put("tenant-b", tenantB);

        routing.setTargetConnectionFactories(targets);
        routing.setLenientFallback(false);
        return routing;
    }
}
```

Ví dụ dùng URL minh họa để thể hiện cách kết nối; không đưa credentials thật vào source code. Trong dự án thực tế, lấy thông tin đăng nhập từ biến môi trường hoặc secret management. Có thể cấu hình `ConnectionFactory` qua builder/options để không ghép URL thủ công.

Các điểm cần chú ý:

- Mỗi tenant có một factory đích.
- `setTargetConnectionFactories` đăng ký map route key tới factory.
- `setLenientFallback(false)` yêu cầu key không khớp phải bị từ chối thay vì âm thầm dùng factory mặc định.
- Ví dụ không đặt default target để route key thiếu cũng không tự động chuyển tới một tenant cụ thể.
- `@Primary` đánh dấu routing factory là connection factory mặc định cho các bean cần inject một `ConnectionFactory`.

Tên bean, qualifier và cơ chế auto-configuration cần được điều chỉnh theo cấu trúc project. Nếu ứng dụng có nhiều `ConnectionFactory`, hãy cấu hình rõ repository/template và transaction manager dùng routing factory.

### 7.1. Cấu hình lenient fallback

`AbstractRoutingConnectionFactory` có thể dùng default target và chế độ fallback. Với dữ liệu nhiều tenant, nên hiểu rõ các trường hợp:

| Route key | Default target | Lenient fallback | Hành vi mong muốn |
| --- | --- | --- | --- |
| Key hợp lệ có trong map | Có/không | Bất kỳ | Chọn factory tương ứng |
| Key không tồn tại trong map | Có | `true` | Có thể dùng default target |
| Key không tồn tại trong map | Có | `false` | Từ chối key không khớp; default chủ yếu dành cho key null |
| Key thiếu | Không | `false` | Không có factory phù hợp, phát lỗi |

Với tenant routing, không nên cấu hình default target là database của một tenant thật. Nếu muốn có database dùng chung cho request không thuộc tenant, hãy biểu diễn route đó bằng một key rõ ràng và chỉ cấp key cho caller hợp lệ.

## 8. Gắn route key vào Reactor Context

Routing factory chỉ đọc context; một thành phần ở phía ngoài phải đặt route key trước khi repository lấy connection.

Ví dụ ở application service hoặc controller:

```java
public Flux<Customer> findCustomersForTenant(String tenantId) {
    return customerRepository.findAll()
            .contextWrite(context -> context.put(
                    TenantRouteContext.ROUTE_KEY,
                    tenantId));
}
```

Khi subscribe publisher, context chứa tenant ID sẽ được truyền upstream tới routing factory.

Trong ứng dụng thực tế, không nên nhận `tenantId` tùy ý từ body/query parameter rồi dùng trực tiếp để định tuyến. Route key cần được xác định từ thông tin đã xác thực, ví dụ tenant claim trong principal hoặc kết quả của một tenant resolver đáng tin cậy.

### 8.1. Đặt context ở WebFlux WebFilter

Nếu mọi thao tác trong một HTTP request cần cùng route, có thể đặt context ở WebFlux filter sau khi xác định và xác thực tenant:

```java
@Component
public class TenantRoutingWebFilter implements WebFilter {

    private final TenantResolver tenantResolver;

    public TenantRoutingWebFilter(TenantResolver tenantResolver) {
        this.tenantResolver = tenantResolver;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return tenantResolver.resolveAuthenticatedTenant(exchange)
                .flatMap(tenantId -> chain.filter(exchange)
                        .contextWrite(context -> context.put(
                                TenantRouteContext.ROUTE_KEY,
                                tenantId)));
    }
}
```

`TenantResolver` trong ví dụ đại diện cho logic xác minh tenant theo principal hoặc chính sách ứng dụng. Filter chỉ đặt route key sau khi resolver trả về tenant hợp lệ.

`contextWrite` được đặt trên publisher của `chain.filter(...)`, nên context có thể được nhìn thấy bởi các thao tác upstream trong request, bao gồm controller, service, transaction interceptor và repository khi chúng tham gia cùng pipeline.

### 8.2. Lấy tenant từ Reactive Security Context

Nếu ứng dụng dùng Spring Security WebFlux, tenant có thể được lấy từ principal đã xác thực:

```java
Mono<String> tenantId = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getPrincipal)
        .cast(TenantAwarePrincipal.class)
        .map(TenantAwarePrincipal::getTenantId);
```

Sau đó có thể đưa giá trị vào context hoặc để `determineCurrentLookupKey()` đọc trực tiếp từ `ReactiveSecurityContextHolder`. Cả hai cách đều phải bảo đảm tenant đã được xác thực và route key được kiểm tra nằm trong tập factory được phép.

Không dùng `SecurityContextHolder` dạng imperative dựa trên ThreadLocal trong reactive flow nếu chưa cấu hình cơ chế context propagation tương ứng. Với WebFlux, dùng `ReactiveSecurityContextHolder`.

## 9. Thứ tự đặt context và transaction boundary

Điểm rất quan trọng là routing key phải có mặt khi transaction manager lấy connection.

Ví dụ dùng `@Transactional`:

```java
public Mono<Order> placeOrderForTenant(String tenantId, Order order) {
    return orderService.placeOrder(order)
            .contextWrite(context -> context.put(
                    TenantRouteContext.ROUTE_KEY,
                    tenantId));
}
```

Giả sử `orderService.placeOrder` là method được Spring proxy áp dụng `@Transactional`. `contextWrite` ở publisher bên ngoài truyền route key tới transaction interceptor khi publisher được subscribe. Transaction manager sau đó yêu cầu routing factory lấy connection và factory có thể đọc đúng key.

Không đặt route key sau khi connection đã được lấy. Nếu pipeline đã bắt đầu transaction và transaction manager đã bind connection, thay đổi context ở một đoạn downstream không thể đổi connection đang được transaction sử dụng.

### 9.1. Dùng TransactionalOperator

Với programmatic transaction, hãy đặt context ở ngoài publisher đã được bọc transaction:

```java
Mono<Order> work = transactionalOperator.transactional(
        orderRepository.save(order));

return work.contextWrite(context -> context.put(
        TenantRouteContext.ROUTE_KEY,
        tenantId));
```

Subscriber context được cung cấp từ `contextWrite` ở cuối chuỗi và có thể được nhìn thấy bởi transaction operator cùng routing factory ở upstream.

Hãy bảo đảm mọi thao tác database trong transaction dùng cùng route key. Một transaction R2DBC thông thường giữ một connection đã được chọn; đổi route key giữa transaction không làm transaction chuyển sang database khác.

### 9.2. Cách đặt context dễ sai

Đừng gọi repository hoặc bắt đầu transaction trước rồi mới tìm tenant bằng một subscription riêng:

```java
// Không nên: route context không thuộc publisher đang được trả về
customerRepository.findAll().subscribe();
return Mono.just("done");
```

Subscription độc lập không chia sẻ lifecycle/context với publisher của caller. Nó cũng khiến lỗi và kết quả truy vấn bị tách khỏi request.

Hãy nối toàn bộ công việc trong một publisher và đặt context tại ranh giới ngoài cùng:

```java
return customerRepository.findAll()
        .collectList()
        .flatMap(this::processCustomers)
        .contextWrite(context -> context.put(
                TenantRouteContext.ROUTE_KEY,
                tenantId));
```

## 10. Kết hợp routing factory với R2dbcTransactionManager

Transaction manager cần dùng chính routing `ConnectionFactory` mà repository sử dụng:

```java
@Bean("routingTransactionManager")
ReactiveTransactionManager routingTransactionManager(
        @Qualifier("routingConnectionFactory") ConnectionFactory routingFactory) {
    return new R2dbcTransactionManager(routingFactory);
}
```

Repository, `R2dbcEntityTemplate`, `DatabaseClient` và transaction manager phải dùng cùng routing factory nếu chúng cần tham gia cùng một transaction.

Khi transaction bắt đầu:

1. Spring gọi `R2dbcTransactionManager`.
2. Transaction manager yêu cầu connection từ routing factory.
3. Routing factory đọc route key trong Reactor Context.
4. Routing factory chọn connection factory đích.
5. Connection được lấy và gắn với transaction context.
6. Các thao tác repository tiếp theo trong transaction dùng connection đã bind.
7. Transaction commit/rollback và connection được trả về factory/pool phù hợp.

Điều này có nghĩa route key phải được đặt trước bước 2. Nếu không, lookup key có thể rỗng và routing thất bại hoặc dùng default theo cấu hình.

### 10.1. Cùng routing factory cho DatabaseClient

Nếu tạo `DatabaseClient` thủ công, hãy dùng routing factory:

```java
@Bean
DatabaseClient databaseClient(
        @Qualifier("routingConnectionFactory") ConnectionFactory routingFactory) {
    return DatabaseClient.create(routingFactory);
}
```

Nếu `DatabaseClient` dùng một target factory riêng, các câu SQL của nó có thể không tham gia transaction được quản lý bởi routing transaction manager.

### 10.2. Tên transaction manager

Nếu có nhiều transaction manager, chỉ rõ tên trong annotation:

```java
@Transactional(transactionManager = "routingTransactionManager")
public Mono<Order> placeOrder(Order order) {
    return orderRepository.save(order);
}
```

Không dựa vào lựa chọn mặc định nếu ứng dụng có nhiều manager và nhiều database. Chỉ định rõ manager giúp tránh transaction được mở trên sai tài nguyên.

## 11. Định tuyến theo tenant trong repository

Repository không cần biết tenant cụ thể:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, UUID> {
}
```

Service cũng có thể tập trung vào nghiệp vụ:

```java
@Service
public class CustomerService {

    private final CustomerRepository customerRepository;

    public CustomerService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    public Flux<Customer> findAll() {
        return customerRepository.findAll();
    }
}
```

Routing được thực hiện ở connection factory. Cùng một repository có thể truy cập database tenant A hoặc B tùy route key trong subscription.

Đây là lợi ích của routing ở tầng connection: domain repository không phải nhận tenant ID trong mọi method signature chỉ để chọn database. Tuy nhiên, service vẫn cần kiểm soát tenant authorization và không nên dựa vào route key như cơ chế duy nhất để bảo vệ dữ liệu.

## 12. Định tuyến theo nhiều nguồn metadata

Route key có thể được xác định từ:

- Tenant claim trong JWT/principal đã xác thực.
- Hostname/subdomain sau khi được kiểm tra với danh sách domain đã đăng ký.
- Một request attribute được tạo bởi filter xác thực.
- Một job metadata được ghi nhận khi message được nhận từ queue.
- Context của một tác vụ nền đã xác định tenant rõ ràng.

Không nên lấy route key từ header tùy ý mà không xác minh. Ví dụ, nếu request gửi `X-Tenant: tenant-b`, ứng dụng phải kiểm tra người dùng có quyền truy cập tenant B trước khi đặt key đó vào context.

Route key cũng không nên chứa connection string do caller cung cấp. Hãy ánh xạ một ID đã xác thực tới factory nằm trong allowlist được cấu hình sẵn.

## 13. Tác vụ nền và message consumer

Không phải mọi pipeline đều bắt đầu từ HTTP request. Một message consumer cũng cần đặt route key trước khi gọi repository:

```java
public Mono<Void> handle(TenantMessage message) {
    String tenantId = tenantResolver.resolve(message);

    return orderService.process(message)
            .then()
            .contextWrite(context -> context.put(
                    TenantRouteContext.ROUTE_KEY,
                    tenantId));
}
```

Trong thực tế, `tenantResolver.resolve` cần xác thực nguồn message và kiểm tra tenant có hợp lệ. Nếu message được xử lý lại, route key vẫn phải được xác định từ metadata đáng tin cậy.

Với scheduled job chạy trên nhiều tenant, có thể tạo một pipeline cho mỗi tenant:

```java
Flux<Void> jobs = Flux.fromIterable(tenantIds)
        .concatMap(tenantId -> processTenant(tenantId)
                .contextWrite(context -> context.put(
                        TenantRouteContext.ROUTE_KEY,
                        tenantId)));
```

`concatMap` xử lý tenant tuần tự. Nếu các tenant độc lập và muốn chạy đồng thời, có thể dùng `flatMap` với giới hạn concurrency. Mỗi inner publisher có context riêng nên route key của tenant này không ghi đè route key của tenant khác.

## 14. Định tuyến và connection pool

Mỗi target `ConnectionFactory` có thể là một pool riêng. Routing factory chọn target factory; target factory chịu trách nhiệm cấp connection theo cấu hình của nó.

Ví dụ nếu có 100 tenant và mỗi tenant có pool tối đa 10 connection, tổng giới hạn lý thuyết có thể lên tới 1.000 connection nếu tất cả pool được sử dụng. Database server có thể không chịu được số connection đó.

Hãy cân nhắc:

- Số lượng tenant/database đang hoạt động.
- `maxSize`, `initialSize` và thời gian acquire timeout của từng pool.
- Tổng connection tối đa mà các database cho phép.
- Pool có được khởi tạo lười hay tạo ngay khi ứng dụng startup.
- Health check và cách đóng pool khi ứng dụng shutdown.
- Tenant ít hoạt động có nên dùng pool dùng chung hay mô hình database/schema khác không.

Không tạo một pool mới cho mỗi request. Target `ConnectionFactory` nên được quản lý như bean/resource lâu dài theo database hoặc nhóm tenant.

## 15. Định tuyến nhiều database không phải transaction phân tán

Routing factory chọn một target `ConnectionFactory` cho một lần lấy connection. Nó không biến nhiều database thành một transaction ACID duy nhất.

Giả sử một request cần:

1. Đọc khách hàng từ database tenant A.
2. Ghi hóa đơn vào database billing.

Nếu hai thao tác dùng hai `ConnectionFactory` khác nhau, `R2dbcTransactionManager` gắn với routing factory tenant A không thể tự rollback thao tác ở database billing.

Một transaction R2DBC thông thường giữ connection đã chọn từ lúc bắt đầu. Thay route key giữa transaction không đổi connection đã bind. Không thiết kế một transaction với kỳ vọng có thể chuyển qua lại nhiều target factory chỉ bằng cách thay Reactor Context.

Nếu cần phối hợp nhiều database, hãy dùng ranh giới transaction riêng và cơ chế nhất quán phân tán phù hợp như saga, outbox, retry idempotent hoặc bước bù trừ. Không gọi hai transaction local là một transaction toàn cục.

## 16. Bảo đảm tenant isolation

Định tuyến đúng database là một lớp bảo vệ, nhưng không thay thế toàn bộ kiểm soát truy cập.

Các nguyên tắc cần áp dụng:

- Xác thực người dùng trước khi xác định tenant.
- Kiểm tra principal được phép truy cập tenant tương ứng.
- Chỉ cho phép route key nằm trong danh sách target factory đã cấu hình.
- Thiếu route key hoặc key không hợp lệ phải thất bại rõ ràng.
- Không dùng default target là database của một tenant cụ thể.
- Không log connection URL, password hoặc secret.
- Kiểm thử để bảo đảm context của request A không rò sang request B.
- Với mô hình shared database, vẫn cần tenant predicate/row-level security ở query/schema.

Một route key hợp lệ chỉ xác định nơi kết nối. Nếu một tenant có thể tự gửi route key của tenant khác, ứng dụng vẫn có thể truy cập nhầm database. Nguồn route key phải là dữ liệu đã được xác thực, không phải một chuỗi tùy ý từ client.

## 17. Trường hợp route key bị thiếu hoặc không hợp lệ

Khi `determineCurrentLookupKey()` trả `Mono.empty()`, routing factory không có lookup key. Nếu có default target, factory có thể dùng default tùy cấu hình. Nếu không có default và không cho phép fallback, thao tác lấy connection sẽ thất bại.

Với ứng dụng multi-tenant, nên có chính sách fail closed:

```java
routing.setLenientFallback(false);
```

Và không khai báo default target nếu mọi request bắt buộc phải có tenant. Khi route key không hợp lệ, trả lỗi rõ ràng và chuyển thành response phù hợp ở tầng web.

Có thể kiểm tra key ngay trong `determineCurrentLookupKey()` để phát lỗi dễ hiểu:

```java
@Override
protected Mono<Object> determineCurrentLookupKey() {
    return Mono.deferContextual(contextView ->
            Mono.justOrEmpty(contextView.getOrEmpty(TenantRouteContext.ROUTE_KEY))
                    .switchIfEmpty(Mono.error(
                            new IllegalStateException("Tenant route is missing"))));
}
```

Ví dụ này dùng `switchIfEmpty` để phát lỗi khi thiếu key. Nếu `AbstractRoutingConnectionFactory` cần tự áp dụng default behavior, hãy chọn một trong hai chính sách nhất quán: trả empty và cấu hình default/fallback, hoặc phát lỗi trực tiếp. Với multi-tenant nghiêm ngặt, phát lỗi rõ ràng thường dễ phát hiện cấu hình sai hơn.

## 18. Định tuyến đọc/ghi hoặc primary/replica

Reactor Context không chỉ có thể mang tenant key. Nó cũng có thể mang mục đích đọc/ghi:

```java
public final class DatabaseRouteContext {
    public static final String ROUTE_KEY = "database-route";

    private DatabaseRouteContext() {
    }
}
```

Các route có thể là `primary` và `replica`. Tuy nhiên, cần lưu ý consistency:

- Ghi vào primary rồi đọc ngay từ replica có thể thấy dữ liệu cũ do replication lag.
- Transaction ghi phải luôn dùng primary.
- Một transaction không nên đổi từ primary sang replica sau khi connection đã được bind.
- Các truy vấn yêu cầu read-after-write consistency cần đọc từ primary hoặc có cơ chế session consistency.

Có thể xác định route dựa trên annotation hoặc metadata use case, nhưng phải bảo đảm route key được đặt trước khi transaction bắt đầu và mọi thao tác trong transaction dùng cùng route.

## 19. Kiểm thử routing bằng hai database

Một integration test rõ ràng nên có hai database riêng, cùng schema nhưng dữ liệu phân biệt. Ví dụ:

- Database A có customer `tenant-a@example.com`.
- Database B có customer `tenant-b@example.com`.

Khi đặt route A, repository chỉ nhìn thấy dữ liệu A; khi đặt route B, repository chỉ nhìn thấy dữ liệu B.

Ví dụ test với Reactor Context:

```java
@Test
void shouldRouteToTenantA() {
    StepVerifier.create(customerRepository.findAll()
            .collectList()
            .contextWrite(context -> context.put(
                    TenantRouteContext.ROUTE_KEY,
                    "tenant-a")))
            .assertNext(customers -> {
                assertTrue(customers.stream()
                        .anyMatch(c -> c.getEmail().equals("tenant-a@example.com")));
                assertFalse(customers.stream()
                        .anyMatch(c -> c.getEmail().equals("tenant-b@example.com")));
            })
            .verifyComplete();
}
```

Test tenant B tương tự với route key `tenant-b`.

### 19.1. Kiểm thử route key thiếu

Nếu hệ thống yêu cầu mọi request phải có route key, hãy xác nhận truy vấn không có context kết thúc bằng lỗi:

```java
StepVerifier.create(customerRepository.findAll().collectList())
        .expectError()
        .verify();
```

Không nên để test chỉ xác nhận query trả empty, vì điều đó có thể che việc routing factory vô tình chọn default database.

### 19.2. Kiểm thử không rò context giữa các request

Chạy hai publisher với hai context khác nhau:

```java
Mono<List<Customer>> tenantA = customerRepository.findAll()
        .collectList()
        .contextWrite(context -> context.put(
                TenantRouteContext.ROUTE_KEY, "tenant-a"));

Mono<List<Customer>> tenantB = customerRepository.findAll()
        .collectList()
        .contextWrite(context -> context.put(
                TenantRouteContext.ROUTE_KEY, "tenant-b"));

StepVerifier.create(Mono.zip(tenantA, tenantB))
        .assertNext(tuple -> {
            assertTrue(tuple.getT1().stream()
                    .allMatch(c -> c.getEmail().endsWith("tenant-a@example.com")
                            || c.getEmail().equals("tenant-a@example.com")));
            assertTrue(tuple.getT2().stream()
                    .allMatch(c -> c.getEmail().equals("tenant-b@example.com")));
        })
        .verifyComplete();
```

Trong test thực tế, nên dùng predicate rõ ràng cho dữ liệu fixture. Mục tiêu là xác nhận hai subscription đồng thời vẫn dùng đúng route riêng, không chia sẻ một biến ThreadLocal mutable.

### 19.3. Kiểm thử transaction với routing

Kiểm tra rằng:

- Route key đã được đặt trước khi transaction manager lấy connection.
- Tất cả thao tác trong cùng transaction sử dụng cùng target database.
- Lỗi ở bước sau rollback thay đổi ở target database đã chọn.
- Đổi context giữa các request không làm đổi connection của transaction đang chạy.
- Connection được trả về pool sau commit, rollback và cancellation.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Luôn truy cập cùng một database | Route key không có trong Reactor Context hoặc default target đang được dùng | Đặt context trước khi lấy connection và kiểm tra fallback |
| Route key luôn rỗng | Dùng ThreadLocal hoặc đọc context sai thời điểm | Dùng `Mono.deferContextual` trong `determineCurrentLookupKey()` |
| `No ConnectionFactory found for lookup key` | Key không có trong target map | Kiểm tra tenant resolver và map key/factory |
| Tenant A đọc được dữ liệu tenant B | Default target sai hoặc route key lấy từ input chưa xác thực | Fail closed, xác thực tenant và kiểm thử isolation |
| `@Transactional` dùng sai database | Transaction manager được cấu hình với target factory khác routing factory | Dùng cùng routing factory cho repository và manager |
| Đổi tenant giữa transaction nhưng không chuyển DB | Connection đã được bind khi transaction bắt đầu | Không đổi route trong transaction; tạo transaction riêng nếu cần |
| Một số truy vấn đi qua DB khác | Repository/DatabaseClient dùng factory riêng | Cấu hình tất cả persistence component với cùng routing factory |
| Context mất trong tác vụ nền | Tạo subscription độc lập hoặc không gắn context cho message | Dùng `contextWrite` trên publisher của từng job |
| Pool cạn connection | Mỗi tenant có pool quá lớn hoặc transaction kéo dài | Giới hạn pool, rút ngắn transaction và theo dõi acquire timeout |
| Test pass nhưng production route sai | Chỉ test một database hoặc dùng default route | Test nhiều database với dữ liệu phân biệt và thiếu-key case |

## 21. Quy trình thiết kế routing dựa trên Reactor Context

Khi xây dựng định tuyến nhiều database, hãy thực hiện theo trình tự:

1. Xác định tiêu chí định tuyến, ví dụ tenant ID, region hoặc read/write role.
2. Xác thực nguồn cung cấp route key trước khi đưa vào context.
3. Tạo một `ConnectionFactory` cho mỗi database hoặc nhóm tài nguyên đích.
4. Kế thừa `AbstractRoutingConnectionFactory` và đọc route key bằng `Mono.deferContextual`.
5. Đăng ký target factory bằng map key rõ ràng.
6. Chọn chính sách default/fallback; với multi-tenant, ưu tiên fail closed khi thiếu hoặc sai key.
7. Đặt route key bằng `contextWrite` ở ngoài publisher trước khi transaction hoặc repository lấy connection.
8. Dùng routing factory cho repository, `DatabaseClient`, template và `R2dbcTransactionManager` cần cùng tham gia transaction.
9. Giữ route key ổn định trong suốt một transaction; không kỳ vọng đổi context sẽ chuyển connection đang bind.
10. Giới hạn pool và concurrency phù hợp với số lượng database/tenant.
11. Kiểm thử hai route độc lập, route thiếu, route sai, transaction rollback và context isolation.

Định tuyến dựa trên Reactor Context cho phép cùng một repository reactive sử dụng nhiều database theo ngữ cảnh của subscription. `AbstractRoutingConnectionFactory` chọn target khi connection được lấy, còn `Mono.deferContextual` đọc route key mà không phụ thuộc thread. Đặt context trước transaction boundary, dùng cùng routing factory ở repository và transaction manager, đồng thời xác thực route key và fail closed khi không hợp lệ để tránh truy cập nhầm dữ liệu giữa các tenant.
