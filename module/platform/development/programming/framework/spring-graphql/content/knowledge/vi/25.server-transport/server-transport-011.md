# `WebGraphQlHandler` trong Spring for GraphQL

`WebGraphQlHandler` là thành phần trung tâm xử lý một GraphQL request ở tầng web của Spring for GraphQL. Nó kết nối chuỗi `WebGraphQlInterceptor` với `ExecutionGraphQlService`, sau đó trả về `WebGraphQlResponse`. HTTP handler và WebSocket handler dùng chung thành phần này để thực thi GraphQL, nhờ đó logic xử lý request không phụ thuộc vào chi tiết của từng transport.

Trong một ứng dụng Spring Boot thông thường, starter GraphQL tự cấu hình các thành phần cần thiết. Khi cần hiểu luồng xử lý, tích hợp interceptor hoặc tự lắp ráp endpoint trong ứng dụng không dùng Boot, cần nắm rõ vai trò của `WebGraphQlHandler`, builder, transport handler và execution service.

## 1. `WebGraphQlHandler` giải quyết vấn đề gì?

GraphQL có thể được gửi qua nhiều transport, chẳng hạn HTTP và WebSocket. Mỗi transport có cách nhận request và gửi response khác nhau, nhưng phần lớn logic GraphQL vẫn giống nhau:

- Đọc GraphQL document, operation name và variables.
- Đưa metadata request vào `ExecutionInput` hoặc `GraphQLContext`.
- Chạy các interceptor chung.
- Gọi GraphQL execution service.
- Quan sát hoặc biến đổi kết quả trước khi trả response.

`WebGraphQlHandler` gom phần xử lý chung này vào một contract duy nhất. Transport handler chịu trách nhiệm chuyển đổi request/response của HTTP hoặc WebSocket; `WebGraphQlHandler` điều phối chuỗi interceptor và phần thực thi GraphQL.

## 2. Vị trí trong kiến trúc server transport

Các thành phần chính có thể hình dung như sau:

```text
                  HTTP request
                       |
                       v
                GraphQlHttpHandler
                       |
                       v
                WebGraphQlHandler <----- GraphQlWebSocketHandler
                       |                         ^
                       v                         |
             WebGraphQlInterceptor chain --------+
                       |
                       v
              ExecutionGraphQlService
                       |
                       v
                  GraphQL Java
                       |
                       v
              WebGraphQlResponse
                       |
                       v
           HTTP response / WebSocket message
```

`WebGraphQlHandler` không tự mở cổng mạng và cũng không tự tạo route HTTP. Nó là lớp xử lý chung được các transport adapter gọi đến.

| Thành phần | Trách nhiệm |
|---|---|
| `GraphQlSource` | Cung cấp schema và cấu hình GraphQL Java như runtime wiring, scalar và instrumentation. |
| `ExecutionGraphQlService` | Thực thi GraphQL request mà không phụ thuộc HTTP hay WebSocket. |
| `WebGraphQlInterceptor` | Can thiệp request/response ở tầng web trước và sau execution. |
| `WebGraphQlHandler` | Kết nối interceptor chain với `ExecutionGraphQlService`. |
| `GraphQlHttpHandler` | Chuyển HTTP request thành GraphQL web request, gọi handler và ghi HTTP response. |
| `GraphQlWebSocketHandler` | Quản lý GraphQL operation trên WebSocket và chuyển từng request vào handler. |

## 3. Luồng xử lý một request

Với HTTP, quá trình thường diễn ra theo thứ tự:

1. Client gửi HTTP request tới endpoint GraphQL.
2. `GraphQlHttpHandler` đọc method, headers, media type và body; sau đó tạo `WebGraphQlRequest`.
3. `WebGraphQlHandler` gọi các `WebGraphQlInterceptor` theo thứ tự đã cấu hình.
4. Interceptor có thể đọc request, bổ sung `ExecutionInput` hoặc `GraphQLContext`, rồi gọi `chain.next(request)`.
5. Interceptor cuối cùng chuyển request tới `ExecutionGraphQlService`.
6. `ExecutionGraphQlService` gọi GraphQL Java để parse, validate và execute operation.
7. Kết quả được bọc thành `WebGraphQlResponse` và đi ngược qua interceptor chain.
8. `GraphQlHttpHandler` chuyển kết quả thành HTTP response.

Với WebSocket, transport handler duy trì connection và quản lý protocol. Mỗi GraphQL operation trên connection vẫn đi qua `WebGraphQlHandler` và interceptor chain. Các callback liên quan đến vòng đời connection hoặc cancellation được bổ sung bởi `WebSocketGraphQlInterceptor`.

## 4. API và cách tạo handler bằng Builder

`WebGraphQlHandler` thuộc package:

```java
import org.springframework.graphql.server.WebGraphQlHandler;
```

API chính:

```java
public interface WebGraphQlHandler {

    static WebGraphQlHandler.Builder builder(
            ExecutionGraphQlService graphQlService);

    Mono<WebGraphQlResponse> handleRequest(WebGraphQlRequest request);
}
```

`builder(...)` nhận `ExecutionGraphQlService`, tức thành phần chịu trách nhiệm thực thi request. Builder cho phép thêm interceptor rồi tạo handler:

```java
WebGraphQlHandler handler = WebGraphQlHandler
    .builder(executionGraphQlService)
    .interceptor(correlationIdInterceptor)
    .interceptor(timeoutInterceptor)
    .build();
```

Có thể truyền nhiều interceptor cùng lúc:

```java
WebGraphQlHandler handler = WebGraphQlHandler
    .builder(executionGraphQlService)
    .interceptors(List.of(
        correlationIdInterceptor,
        tenantContextInterceptor,
        timeoutInterceptor
    ))
    .build();
```

Hai cách trên tương đương về mục đích. `interceptor(...)` thuận tiện khi thêm từng thành phần; `interceptors(...)` phù hợp khi danh sách đã được tạo trước.

`handleRequest(WebGraphQlRequest)` thực thi request và trả `Mono<WebGraphQlResponse>`. Đây là API bất đồng bộ; không gọi `block()` bên trong interceptor hoặc transport adapter để chờ kết quả.

## 5. Handler phối hợp với `ExecutionGraphQlService`

`WebGraphQlHandler` không tự parse schema hoặc cấu hình resolver. Nó ủy quyền phần thực thi cho `ExecutionGraphQlService`.

Luồng cấu hình tổng quát:

```text
schema SDL + runtime wiring
            |
            v
       GraphQlSource
            |
            v
  ExecutionGraphQlService
            |
            v
    WebGraphQlHandler
            |
            v
  HTTP / WebSocket transport
```

`GraphQlSource` là nơi cấu hình schema, scalar, type resolver và data fetcher. `ExecutionGraphQlService` sử dụng GraphQL source để thực thi request. Vì execution service không phụ thuộc transport, nó cũng có thể được kiểm thử trực tiếp mà không cần tạo HTTP hoặc WebSocket request.

Trong Spring Boot, các bean GraphQL cần thiết thường được auto-configure từ schema và annotated controller. Khi tự cấu hình, có thể tạo `DefaultExecutionGraphQlService` từ `GraphQlSource`, sau đó truyền service vào `WebGraphQlHandler.builder(...)`.

## 6. Thêm interceptor vào handler chain

Interceptor là thành phần riêng lẻ; handler là nơi kết hợp chúng. Một interceptor có thể đọc HTTP header, thêm metadata vào GraphQL context và tiếp tục request:

```java
@Component
class TenantContextInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String tenantId = request.getHeaders().getFirst("X-Tenant-Id");

        request.configureExecutionInput((input, builder) ->
            builder.graphQLContext(context ->
                context.put("tenantId", tenantId)
            ).build()
        );

        return chain.next(request);
    }
}
```

Resolver có thể nhận context value:

```java
@QueryMapping
List<Project> projects(@ContextValue("tenantId") String tenantId) {
    return projectService.findForTenant(tenantId);
}
```

`chain.next(request)` chuyển request sang interceptor tiếp theo hoặc execution service. Nếu interceptor không gọi `chain.next`, request sẽ không đi tới GraphQL execution, trừ khi interceptor chủ động tạo response thay thế.

Không nên tin cậy trực tiếp `X-Tenant-Id` do client gửi nếu tenant phải được xác định từ danh tính đã xác thực. Ví dụ trên minh họa việc truyền metadata; trong ứng dụng thật, cần kiểm tra quyền và nguồn tenant ở security/service layer.

## 7. Xử lý response trong interceptor chain

Interceptor có thể thực hiện công việc sau khi GraphQL execution hoàn tất. Ví dụ thêm correlation ID vào HTTP response header:

```java
@Component
class CorrelationResponseInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String correlationId = request.getHeaders().getFirst("X-Correlation-Id");

        return chain.next(request).doOnNext(response -> {
            if (correlationId != null) {
                response.getResponseHeaders()
                    .set("X-Correlation-Id", correlationId);
            }
        });
    }
}
```

`WebGraphQlResponse` chứa kết quả GraphQL cùng thông tin phục vụ web transport, trong đó có response headers và khả năng biến đổi response qua `transform(...)`.

Đối với WebSocket, HTTP handshake đã hoàn tất trước khi các GraphQL operation được gửi. Header được thêm vào response của một operation không thể trở thành HTTP response header mới cho từng message WebSocket. Nếu cần gửi metadata trong WebSocket protocol, phải dùng cơ chế phù hợp với protocol hoặc payload GraphQL.

## 8. Kiểm tra request validation error

Một điểm quan trọng của handler chain là interceptor có thể quan sát cả lỗi xảy ra trước khi data fetcher chạy, ví dụ parse hoặc validation error. `DataFetcherExceptionResolver` chỉ xử lý exception từ quá trình data fetching; nó không phải nơi xử lý mọi lỗi request.

Ví dụ interceptor ghi nhận response không hợp lệ:

```java
@Component
class RequestValidationLoggingInterceptor implements WebGraphQlInterceptor {

    private static final Logger log =
        LoggerFactory.getLogger(RequestValidationLoggingInterceptor.class);

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        return chain.next(request).doOnNext(response -> {
            if (!response.isValid()) {
                log.debug("GraphQL request {} returned {} errors",
                    request.getId(), response.getErrors().size());
            }
        });
    }
}
```

Nếu cần biến đổi error list, có thể dùng `response.transform(builder -> builder.errors(errors).build())`. Hãy giữ `message`, `locations`, `path` và `extensions` cần thiết; không xóa lỗi chỉ để response trông như thành công.

## 9. Cấu hình `WebGraphQlHandler` trong Spring Boot

Với `spring-boot-starter-graphql`, Spring Boot tự cấu hình schema, execution service, web handler và transport endpoint dựa trên các starter đang có. Ứng dụng thường không cần tự gọi `WebGraphQlHandler.builder(...)`.

Để thêm interceptor, chỉ cần khai báo bean:

```java
@Configuration(proxyBeanMethods = false)
class GraphQlWebConfiguration {

    @Bean
    WebGraphQlInterceptor correlationIdInterceptor() {
        return new CorrelationIdInterceptor();
    }
}
```

Boot phát hiện các bean `WebGraphQlInterceptor` và đăng ký vào web transport chain. Có thể dùng `@Order` hoặc triển khai `Ordered` khi nhiều interceptor phụ thuộc thứ tự.

Một số điểm cấu hình transport thường gặp:

| Cấu hình | Mục đích |
|---|---|
| GraphQL HTTP path | Đường dẫn endpoint HTTP; mặc định thường là `/graphql`. |
| `spring.graphql.websocket.path` | Bật và chỉ định đường dẫn endpoint GraphQL WebSocket. |
| HTTP methods | Điều khiển các method HTTP được chấp nhận. |
| CORS | Cho phép browser từ origin phù hợp truy cập endpoint. |

HTTP endpoint được cấu hình mặc định bởi Boot. GraphQL WebSocket endpoint thường tắt mặc định; cần dependency WebSocket phù hợp với Spring MVC hoặc dùng WebFlux, đồng thời đặt `spring.graphql.websocket.path`. Tên property HTTP path có thể khác giữa các dòng Spring Boot; kiểm tra reference của đúng phiên bản dự án.

## 10. Tự lắp ráp handler trong ứng dụng không dùng Boot

Nếu ứng dụng không dùng Spring Boot auto-configuration, cần tự tạo các thành phần GraphQL và transport. Sau khi có `ExecutionGraphQlService`, có thể xây dựng handler:

```java
WebGraphQlHandler webGraphQlHandler = WebGraphQlHandler
    .builder(executionGraphQlService)
    .interceptors(List.of(
        correlationIdInterceptor,
        timeoutInterceptor
    ))
    .build();
```

Với Spring MVC functional endpoint, `GraphQlHttpHandler` là adapter HTTP sử dụng `WebGraphQlHandler`:

```java
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.server.webmvc.GraphQlHttpHandler;
import org.springframework.graphql.server.webmvc.GraphQlRequestPredicates;
import org.springframework.web.servlet.function.RequestPredicate;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

@Bean
RouterFunction<ServerResponse> graphQlRouterFunction(
        WebGraphQlHandler webGraphQlHandler) {

    GraphQlHttpHandler httpHandler = new GraphQlHttpHandler(webGraphQlHandler);
    RequestPredicate predicate = GraphQlRequestPredicates.graphQlHttp("/graphql");

    return RouterFunctions.route()
        .route(predicate, httpHandler::handleRequest)
        .build();
}
```

Với Spring WebFlux, dùng các adapter tương ứng trong package `org.springframework.graphql.server.webflux`. Không trộn handler MVC với router function WebFlux.

Đây là ví dụ về việc lắp ráp HTTP endpoint. Nếu cần WebSocket, phải cấu hình thêm WebSocket handler và mapping phù hợp cho stack MVC hoặc WebFlux. Spring Boot thường đơn giản hóa các bước này.

## 11. `WebSocketGraphQlInterceptor` trong handler chain

`WebSocketGraphQlInterceptor` mở rộng `WebGraphQlInterceptor` với các callback liên quan tới vòng đời WebSocket connection và việc client hủy subscription. Nó vẫn tham gia xử lý từng GraphQL request trên connection.

Một handler chain có thể chứa nhiều `WebGraphQlInterceptor`, nhưng chỉ được có tối đa một interceptor thuộc loại `WebSocketGraphQlInterceptor`. Handler cung cấp `getWebSocketInterceptor()` để transport WebSocket lấy interceptor đặc thù đó.

Ví dụ use case của WebSocket interceptor:

- Xử lý dữ liệu từ message `connection_init`.
- Xác thực và thiết lập context cho connection.
- Quan sát khi connection bắt đầu hoặc kết thúc.
- Nhận biết client cancellation để giải phóng tài nguyên subscription.

Với HTTP-only application, không cần triển khai `WebSocketGraphQlInterceptor`. Với authentication trên WebSocket, có thể dùng interceptor có sẵn của Spring for GraphQL thay vì tự xử lý protocol nếu phù hợp.

## 12. Context propagation và `ContextSnapshotFactory`

Trong reactive application, request có thể chuyển qua nhiều thread. Dữ liệu trong Reactor Context không tự động đồng nhất với `ThreadLocal` của thư viện khác. `WebGraphQlHandler.Builder` hỗ trợ cấu hình `ContextSnapshotFactory` để hỗ trợ truyền `ThreadLocal` và Reactor context giữa transport layer và GraphQL execution layer.

Ví dụ về builder với context snapshot factory:

```java
WebGraphQlHandler handler = WebGraphQlHandler
    .builder(executionGraphQlService)
    .contextSnapshotFactory(contextSnapshotFactory)
    .interceptor(correlationIdInterceptor)
    .build();
```

API `contextSnapshotFactory(...)` được bổ sung từ Spring for GraphQL 1.3.0. Chỉ cấu hình khi ứng dụng thực sự cần truyền context giữa Reactor và `ThreadLocal`; không nên dùng nó thay cho `GraphQLContext` để truyền dữ liệu nghiệp vụ giữa các data fetcher.

`GraphQLContext` phù hợp để truyền dữ liệu theo từng GraphQL execution, như tenant đã xác thực, correlation ID hoặc locale. Context snapshot chủ yếu hỗ trợ tích hợp với cơ chế context propagation ở các tầng khác.

## 13. Timeout và cancellation

Spring for GraphQL cung cấp `TimeoutWebGraphQlInterceptor` để giới hạn thời gian xử lý request qua web transports:

```java
@Configuration(proxyBeanMethods = false)
class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(Duration.ofSeconds(5));
    }
}
```

Trong Spring Boot, khai báo bean là đủ để interceptor được thêm vào web chain. Nếu timeout xảy ra, interceptor phát tín hiệu cancellation lên chain; reactive data fetcher có thể nhận cancellation và dừng công việc đang chạy nếu upstream hỗ trợ.

Timeout cần được chọn theo loại operation. Một query đọc cache có thể có timeout ngắn; operation truy vấn dữ liệu lớn có thể cần giới hạn riêng. Subscription dài hạn không nên bị áp dụng cùng timeout ngắn như query thông thường nếu mục đích của nó là giữ stream mở.

## 14. Kiểm thử handler bằng `WebGraphQlTester`

`WebGraphQlTester` kiểm thử request ở server side nhưng vẫn đi qua `WebGraphQlInterceptor` chain. Đây là cách hữu ích để xác minh interceptor đọc header, bổ sung context và response được xử lý đúng.

Tạo tester từ handler:

```java
WebGraphQlTester tester = WebGraphQlTester.builder(webGraphQlHandler)
    .headers(headers -> headers.set("X-Tenant-Id", "tenant-42"))
    .build();
```

Giả sử resolver đọc tenant từ GraphQL context:

```java
@QueryMapping
String currentTenant(@ContextValue("tenantId") String tenantId) {
    return tenantId;
}
```

Test:

```java
tester.document("""
        query {
            currentTenant
        }
        """)
    .execute()
    .path("currentTenant")
    .entity(String.class)
    .isEqualTo("tenant-42");
```

Test này kiểm tra cả handler lẫn interceptor chain. Nó không mở HTTP socket thực tế; nếu cần kiểm thử HTTP serialization, status code, CORS hoặc network behavior, dùng `HttpGraphQlTester` với `WebTestClient`. Nếu cần kiểm thử protocol WebSocket, dùng `WebSocketGraphQlTester`.

Các trường hợp nên kiểm thử:

- Interceptor được gọi trước execution và thêm đúng `GraphQLContext`.
- Header thiếu hoặc sai định dạng được xử lý theo chính sách.
- Response header được thêm đúng với HTTP transport.
- Validation error được quan sát đúng.
- Exception từ data fetcher vẫn được xử lý qua exception resolver.
- Interceptor chain chạy theo thứ tự đã cấu hình.
- Timeout phát cancellation và không để lại công việc reactive ngoài ý muốn.
- WebSocket-specific interceptor nhận đúng callback vòng đời và cancellation.

## 15. Phân biệt `WebGraphQlHandler` với các handler/interceptor khác

| Thành phần | Phạm vi | Vai trò |
|---|---|---|
| `WebGraphQlHandler` | HTTP và WebSocket | Điều phối interceptor chain và execution service. |
| `GraphQlHttpHandler` | HTTP | Chuyển đổi HTTP request/response và gọi web handler. |
| `GraphQlWebSocketHandler` | WebSocket | Quản lý GraphQL WebSocket protocol và gọi web handler cho operation. |
| `WebGraphQlInterceptor` | Web request/response | Can thiệp request/response trong chain. |
| `WebSocketGraphQlInterceptor` | WebSocket connection và request | Mở rộng interceptor với callback vòng đời connection/cancellation. |
| `ExecutionGraphQlService` | Transport-agnostic | Thực thi GraphQL operation bằng GraphQL Java. |
| `RSocketQlInterceptor` | RSocket | Intercept GraphQL request qua RSocket; không thuộc `WebGraphQlHandler`. |

Chọn thành phần theo đúng ranh giới cần xử lý. Không dùng `WebGraphQlHandler` để thay thế `GraphQlSource`, cũng không dùng `GraphQlHttpHandler` để chứa logic nghiệp vụ của từng field.

## 16. Lỗi thường gặp

**Nhầm handler với HTTP endpoint.** `WebGraphQlHandler` không tự mở port hoặc tạo route. Cần transport adapter như `GraphQlHttpHandler` và cấu hình route, hoặc để Spring Boot tự cấu hình.

**Truyền nhầm `GraphQlSource` vào builder.** `WebGraphQlHandler.builder(...)` nhận `ExecutionGraphQlService`. Hãy tạo hoặc inject đúng service thực thi GraphQL.

**Tự tạo handler trong Spring Boot mà không cần thiết.** Boot đã tự cấu hình handler và transport. Nếu chỉ cần thêm logging, context hoặc timeout, khai báo `WebGraphQlInterceptor` bean thường là đủ.

**Quên gọi `chain.next(request)`.** Request không tới execution service nếu interceptor không tiếp tục chain và không tạo response thay thế.

**Gọi chain nhiều lần.** Một request có thể bị thực thi nhiều lần và gây side effect lặp. Thông thường chỉ gọi `chain.next(request)` đúng một lần.

**Dùng `block()` hoặc `subscribe()` trong interceptor.** Việc này làm mất reactive flow, có thể chặn thread và khiến cancellation không truyền đúng. Hãy compose từ `Mono` do chain trả về.

**Đưa logic nghiệp vụ vào interceptor.** Interceptor phù hợp với concern xuyên suốt request như correlation ID, metadata, timeout hoặc response header. Quy tắc domain nên nằm trong service/resolver.

**Nhầm HTTP response header với GraphQL response data.** `getResponseHeaders()` thay đổi header transport, không thêm field vào phần `data` của GraphQL.

**Cấu hình nhiều `WebSocketGraphQlInterceptor`.** Một handler chain chỉ hỗ trợ tối đa một interceptor thuộc loại này. Kết hợp callback WebSocket cần thiết trong một interceptor.

**Kiểm thử handler nhưng cho rằng đã kiểm thử transport thật.** `WebGraphQlTester` kiểm tra handler và interceptor chain; dùng HTTP/WebSocket tester khi cần xác minh serialization và protocol.

## Kết luận

`WebGraphQlHandler` là lớp điều phối chung cho GraphQL qua HTTP và WebSocket. Nó nhận `ExecutionGraphQlService`, tạo interceptor chain bằng builder và xử lý từng `WebGraphQlRequest` để trả `Mono<WebGraphQlResponse>`. Transport adapter như `GraphQlHttpHandler` hoặc `GraphQlWebSocketHandler` chịu trách nhiệm giao tiếp với client. Trong Spring Boot, thường chỉ cần khai báo interceptor bean; trong standalone setup, tự tạo handler rồi gắn vào transport. Hiểu rõ ranh giới giữa handler, execution service, transport adapter và interceptor giúp cấu hình server nhất quán, dễ kiểm thử và không trộn logic transport với nghiệp vụ.

## Tài liệu tham khảo

- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Standalone Setup](https://docs.spring.io/spring-graphql/reference/standalone-setup.html)
- [Spring for GraphQL API — `WebGraphQlHandler`](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/WebGraphQlHandler.html)
- [Spring for GraphQL — Testing `WebGraphQlHandler`](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
