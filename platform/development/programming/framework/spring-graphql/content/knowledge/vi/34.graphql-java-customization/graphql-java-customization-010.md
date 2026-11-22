# GraphQLContext customization trong Spring for GraphQL

Trong một GraphQL operation, nhiều resolver có thể cần dùng chung thông tin của request như tenant, người dùng đã xác thực, locale, correlation ID hoặc feature flags. Nếu truyền những giá trị này qua từng tham số nghiệp vụ, chữ ký resolver sẽ nhanh chóng trở nên khó quản lý. GraphQL Java cung cấp `GraphQLContext` để giữ dữ liệu dùng chung trong phạm vi một execution; Spring for GraphQL bổ sung interceptor và cơ chế bind context vào controller method.

`GraphQLContext` được tạo cho từng lần thực thi GraphQL và có thể được truy cập từ nhiều data fetcher trong cùng operation. Có thể đưa dữ liệu vào context từ `ExecutionInput`, `WebGraphQlInterceptor` hoặc instrumentation, rồi đọc bằng `GraphQLContext`, `DataFetchingEnvironment` hoặc `@ContextValue`. Với dữ liệu chỉ cần truyền xuống một nhánh field, dùng local context qua `DataFetcherResult` và `@LocalContextValue`.

Sau bài này, bạn có thể:

- Hiểu vòng đời và phạm vi của `GraphQLContext`.
- Phân biệt main context, local context, Reactor Context và Spring Security context.
- Tạo context bằng `ExecutionInput.Builder`.
- Bổ sung metadata vào context qua `WebGraphQlInterceptor`.
- Dùng `HttpRequestHeaderInterceptor` cho header phù hợp.
- Đọc context trong `@QueryMapping`, `@SchemaMapping`, data fetcher và batch loader.
- Truyền dữ liệu xuống một nhánh bằng `DataFetcherResult`.
- Hiểu context propagation với WebFlux, Spring MVC, DataLoader, WebSocket và RSocket.
- Thiết kế context an toàn theo request, tenant và quyền truy cập.
- Kiểm thử context injection, local context và request isolation.

## 1. GraphQLContext giải quyết vấn đề gì?

Một operation có thể gọi nhiều resolver ở nhiều cấp:

```graphql
query Dashboard {
    currentUser {
        id
        name
        orders {
            id
            total
        }
    }
    recommendations {
        id
        title
    }
}
```

Các resolver `currentUser`, `orders` và `recommendations` có thể cần cùng tenant, locale hoặc thông tin người dùng. Nếu mỗi resolver tự đọc HTTP header, truy cập `ThreadLocal` hoặc lặp lại logic lấy security context, code sẽ phụ thuộc transport và khó kiểm thử.

GraphQLContext cung cấp một nơi chung cho metadata của execution. Interceptor có thể đưa metadata vào một lần trước khi GraphQL Java thực thi; các data fetcher sau đó đọc lại giá trị đó mà không cần client truyền lặp trong mọi field argument.

Các giá trị thường phù hợp với context:

- Tenant đã được xác thực và kiểm tra quyền.
- Actor/user ID hoặc một principal snapshot an toàn.
- Correlation ID, trace metadata và request origin.
- Locale hoặc timezone của request.
- Feature flags đã được server xác định.
- Policy hoặc service facade gắn với request.

Context là dữ liệu nội bộ phục vụ execution. Nó không tự xuất hiện trong GraphQL response và không phải một phần của schema mà client có thể query trực tiếp.

## 2. GraphQLContext là gì?

`graphql.GraphQLContext` là một cấu trúc key-value của GraphQL Java. Context được gắn với một lần execution và có thể truy cập từ `ExecutionInput`, `Instrumentation` và `DataFetchingEnvironment`.

```java
GraphQLContext context = GraphQLContext.newContext()
        .put("tenantId", "tenant-42")
        .put("correlationId", "req-9f81")
        .build();
```

`GraphQLContext` hỗ trợ truy cập theo key, kiểm tra key tồn tại và cập nhật giá trị. Cấu trúc bên trong được thiết kế thread-safe để nhiều resolver có thể truy cập trong một execution. Tuy vậy, nên khởi tạo các giá trị trước khi bắt đầu resolve và ưu tiên dùng value object bất biến. Việc nhiều resolver cùng thay đổi một object mutable trong context vẫn có thể gây race condition ở chính object đó.

Key và value được đưa vào context phải khác `null`. Nếu một giá trị không có, hãy bỏ key khỏi context, dùng `Optional` ở nơi đọc hoặc dùng một giá trị mặc định rõ ràng. Không gọi `put(key, null)`.

## 3. Phân biệt các loại context

Tên gọi “context” xuất hiện ở nhiều lớp của ứng dụng. Cần phân biệt chúng trước khi chọn cách truyền dữ liệu:

| Loại | Phạm vi | Mục đích |
| --- | --- | --- |
| `GraphQLContext` | Toàn bộ một GraphQL execution | Metadata dùng chung cho resolver, instrumentation và batch loader |
| Local context | Một nhánh của cây field và các field con | Dữ liệu chỉ cần truyền từ parent resolver xuống descendants |
| Reactor `Context` | Một reactive subscription chain | Truyền metadata trong `Mono`/`Flux` mà không phụ thuộc thread |
| Spring Security context | Authentication hiện tại | Principal, Authentication và quyền của request |
| HTTP request attributes | Một HTTP request | Metadata do web filter/interceptor đặt ở transport layer |
| GraphQL variables/arguments | Operation hoặc field theo schema | Dữ liệu nghiệp vụ do client gửi |

Không dùng GraphQL variables để thay thế metadata nội bộ. Ví dụ tenant hoặc user identity phải được xác định từ security layer, không lấy từ một argument do client tự khai báo rồi tin cậy.

## 4. Tạo GraphQLContext bằng ExecutionInput

Khi gọi GraphQL Java trực tiếp, có thể thêm context vào `ExecutionInput.Builder`:

```java
ExecutionInput executionInput = ExecutionInput.newExecutionInput()
        .query("{ books { id title } }")
        .graphQLContext(context -> context
                .put("tenantId", "tenant-42")
                .put("correlationId", "req-9f81"))
        .build();

ExecutionResult result = graphQL.execute(executionInput);
```

`graphQLContext(...)` nhận một `Consumer<GraphQLContext.Builder>` hoặc một `Map` chứa các giá trị context. Dạng builder giúp khai báo từng key và tránh phải tạo map tạm.

GraphQL Java vẫn giữ API `ExecutionInput.Builder.context(Object)` cũ, nhưng API đó đã deprecated. Khi cần context cho data fetcher, dùng `graphQLContext(...)` và `ExecutionInput.getGraphQLContext()`.

Trong ứng dụng Spring Boot, phần lớn HTTP/ WebSocket request đi qua `WebGraphQlHandler` và `WebGraphQlInterceptor`. Không cần tự tạo `ExecutionInput` cho từng request nếu interceptor đã là nơi phù hợp để bổ sung context.

## 5. Bổ sung context bằng WebGraphQlInterceptor

`WebGraphQlInterceptor` chạy trước và sau GraphQL Java execution đối với HTTP và WebSocket. Interceptor có thể đọc thông tin của transport, tùy chỉnh `ExecutionInput`, thêm response header hoặc xử lý `ExecutionResult`.

Ví dụ thêm correlation ID và locale vào context:

```java
import java.util.Locale;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class RequestContextInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        String correlationId = request.getHeaders().getFirst("X-Correlation-Id");
        Locale locale = request.getLocale() != null ? request.getLocale() : Locale.ROOT;

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context -> {
                    if (correlationId != null && !correlationId.isBlank()) {
                        context.put("correlationId", correlationId);
                    }
                    context.put("requestLocale", locale);
                }).build());

        return chain.next(request);
    }
}
```

`request.configureExecutionInput(...)` cập nhật `ExecutionInput` mà Spring chuẩn bị cho GraphQL Java. Context được gắn với operation hiện tại; resolver trong operation có thể đọc lại `correlationId` và `requestLocale`.

Trong ví dụ, correlation ID là metadata để log và trace. Nếu client không gửi header, context không chứa key đó. Không đưa `null` vào GraphQLContext.

## 6. Dùng HttpRequestHeaderInterceptor có sẵn

Nếu chỉ cần sao chép một số HTTP header vào GraphQLContext, Spring for GraphQL có `HttpRequestHeaderInterceptor`:

```java
@Configuration(proxyBeanMethods = false)
public class GraphQlInterceptorConfiguration {

    @Bean
    HttpRequestHeaderInterceptor requestHeaderInterceptor() {
        return HttpRequestHeaderInterceptor.builder()
                .mapHeader("X-Correlation-Id")
                .build();
    }
}
```

Sau đó controller có thể đọc giá trị bằng `@ContextValue`:

```java
@Controller
public class RequestInfoController {

    @QueryMapping
    public String requestInfo(@ContextValue("X-Correlation-Id") String correlationId) {
        return correlationId;
    }
}
```

Interceptor này hữu ích cho header metadata đơn giản. Nếu cần chuẩn hóa, xác thực hoặc kết hợp nhiều giá trị, hãy viết `WebGraphQlInterceptor` riêng để kiểm soát logic.

Không tự động tin mọi header. Header như `X-Tenant-Id`, `X-User-Id` hoặc `X-Role` có thể do client tự gửi. Chỉ đưa chúng vào context sau khi gateway/security filter đã xác thực và kiểm tra giá trị. Với identity, ưu tiên Spring Security principal thay vì lấy trực tiếp từ header.

## 7. Đọc context trong annotated controller

Có hai cách phổ biến: nhận toàn bộ `GraphQLContext` hoặc bind một key bằng `@ContextValue`.

Nhận toàn bộ context:

```java
@QueryMapping
public List<Book> books(GraphQLContext context) {
    String tenantId = context.get("tenantId");
    return bookService.findVisibleToTenant(tenantId);
}
```

Bind một key cụ thể:

```java
@QueryMapping
public List<Book> books(@ContextValue("tenantId") String tenantId) {
    return bookService.findVisibleToTenant(tenantId);
}
```

`@ContextValue` đọc attribute từ main GraphQLContext của `DataFetchingEnvironment`. Tên key được chỉ định qua `name` hoặc alias `value`.

Mặc định `required = true`: nếu key không có, Spring báo lỗi khi bind method argument. Nếu key thực sự tùy chọn, có thể dùng `required = false` hoặc `Optional`:

```java
@QueryMapping
public List<Book> books(
        @ContextValue(name = "preferredLocale", required = false)
        Optional<Locale> preferredLocale) {

    return bookService.findAll(preferredLocale.orElse(Locale.ROOT));
}
```

Không dùng `@ContextValue` để đọc GraphQL field argument. Field argument thuộc `@Argument`; context là metadata được server đưa vào execution.

## 8. Đọc context từ DataFetchingEnvironment

Khi viết data fetcher trực tiếp hoặc cần truy cập nhiều thông tin execution, dùng `DataFetchingEnvironment`:

```java
DataFetcher<List<Book>> booksFetcher = environment -> {
    GraphQLContext context = environment.getGraphQlContext();
    String tenantId = context.get("tenantId");
    return bookService.findVisibleToTenant(tenantId);
};
```

`environment.getGraphQlContext()` trả main context. `environment.getLocalContext()` trả local context được parent field truyền xuống, nếu có.

Với annotated controller, không cần nhận `DataFetchingEnvironment` chỉ để đọc một key đơn giản; `@ContextValue` thường rõ ràng hơn. Dùng environment khi cần cả selection set, execution path, source object, arguments hoặc các thông tin GraphQL Java khác.

## 9. Truyền dữ liệu xuống một nhánh bằng local context

Main GraphQLContext phù hợp cho dữ liệu dùng chung toàn operation. Nếu một resolver đã tải sẵn dữ liệu chỉ có các field con của nó cần dùng, hãy cân nhắc local context để không đưa dữ liệu đó vào phạm vi toàn query.

Spring controller có thể trả `DataFetcherResult<T>` và gắn local context:

```java
@QueryMapping
public DataFetcherResult<Book> bookById(@Argument Long id) {
    BookAndAuthor result = bookService.findBookAndAuthor(id);

    GraphQLContext localContext = GraphQLContext.newContext()
            .put("prefetchedAuthor", result.author())
            .build();

    return DataFetcherResult.<Book>newResult()
            .data(result.book())
            .localContext(localContext)
            .build();
}
```

Field con đọc local value:

```java
@SchemaMapping(typeName = "Book", field = "relatedBooks")
public List<Book> relatedBooks(
        Book book,
        @LocalContextValue("prefetchedAuthor") Author author) {

    return bookService.findRelatedBooks(book, author);
}
```

Local context được truyền xuống các field con của kết quả parent và các nhánh bên dưới theo execution tree. Nó không phải kho dữ liệu toàn request và không tự động xuất hiện ở các nhánh sibling khác.

## 10. Phân biệt @ContextValue và @LocalContextValue

Hai annotation có tên gần giống nhưng đọc từ hai nơi khác nhau:

| Annotation | Nguồn dữ liệu | Phạm vi |
| --- | --- | --- |
| `@ContextValue` | Main `GraphQLContext` | Toàn bộ execution |
| `@LocalContextValue` | Local context trong `DataFetchingEnvironment` | Một nhánh field và descendants |

Ví dụ dùng `@ContextValue` cho tenant ID vì mọi resolver trong request đều cần tenant đã xác thực. Dùng `@LocalContextValue` cho `prefetchedAuthor` vì chỉ `Book.relatedBooks` và các field con của nhánh đó cần dùng dữ liệu đã tải sẵn.

Đừng đưa dữ liệu riêng của một parent object vào main context nếu local context đã giải quyết được. Làm vậy có thể tạo xung đột khi nhiều parent field cùng ghi một key hoặc khi các resolver chạy đồng thời.

## 11. GraphQLContext trong BatchLoaderRegistry

Spring for GraphQL cung cấp `BatchLoaderRegistry` để đăng ký batch loader. Batch loading function có thể đọc cùng GraphQLContext mà các `@SchemaMapping` method nhìn thấy.

```java
@Configuration
public class AuthorBatchConfiguration {

    public AuthorBatchConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) -> {
                    String tenantId = environment.getContext().get("tenantId");
                    return authorService.findVisibleByIds(tenantId, authorIds)
                            .collectMap(Author::id);
                });
    }
}
```

Resolver sử dụng loader:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorLoader) {

    return authorLoader.load(book.authorId());
}
```

`BatchLoaderRegistry` do Spring quản lý sẽ đăng ký DataLoader theo từng request và hỗ trợ context propagation cho batch function. Đây là lý do nên dùng registry của Spring thay vì tự tạo một DataLoader toàn cục hoặc tự đăng ký loader trực tiếp rồi bỏ qua tích hợp context.

Với quan hệ đơn giản, `@BatchMapping` cũng có thể nhận `GraphQLContext` hoặc `@ContextValue` trực tiếp:

```java
@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<Book, Author>> authors(
        List<Book> books,
        @ContextValue("tenantId") String tenantId) {

    Set<Long> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

    return authorService.findVisibleByIds(tenantId, authorIds)
            .collectMap(Author::id)
            .map(authorsById -> {
                Map<Book, Author> result = new HashMap<>();
                for (Book book : books) {
                    Author author = authorsById.get(book.authorId());
                    if (author != null) {
                        result.put(book, author);
                    }
                }
                return result;
            });
}
```

Method này minh họa việc dùng tenant context trong batch mapping. Nếu không tìm thấy tác giả, key của book đó không xuất hiện trong map và field sẽ resolve thành null; schema cần cho phép giá trị null hoặc resolver phải áp dụng contract lỗi phù hợp. Dùng `BatchLoaderRegistry` nếu cần kiểm soát key, options hoặc logic batch phức tạp hơn.

Vì `Book` được dùng làm key của `Map<Book, Author>`, class `Book` cần có `equals()` và `hashCode()` ổn định. Với entity mutable, tránh thay đổi các field tham gia equality/hash code trong thời gian object đang được dùng làm map key.

## 12. Local context trong batch loading

`BatchLoaderEnvironment` cung cấp hai loại dữ liệu context:

- `getContext()` trả main GraphQLContext chung của execution.
- `getKeyContexts()` cung cấp local context tương ứng với từng key được đưa vào DataLoader.

Điều này hữu ích khi mỗi lần `DataLoader.load(key, localContext)` được gọi với thông tin riêng của parent. Batch function có thể dùng chung tenant từ main context và dùng key context để xử lý từng lần load.

Không giả định mọi key trong một batch có cùng local context. Nếu batch logic phụ thuộc local context, cần giữ mapping đúng giữa từng key và context của nó. Nếu thông tin filter làm thay đổi kết quả, hãy cân nhắc đưa filter vào composite key thay vì dựa vào một context mutable dùng chung.

## 13. GraphQLContext và Reactor Context trong WebFlux

GraphQLContext và Reactor Context phục vụ hai mục đích khác nhau:

- GraphQLContext là map của GraphQL execution và có thể được đọc trực tiếp trong data fetcher.
- Reactor Context thuộc reactive subscription chain và được đọc bằng `deferContextual` trong `Mono`/`Flux`.

Spring for GraphQL hỗ trợ truyền Reactor Context từ WebFlux request chain tới reactive data fetcher. Một `WebGraphQlInterceptor` có thể bổ sung giá trị vào Reactor Context bằng `contextWrite`:

```java
@Component
public class ReactorMetadataInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        String correlationId = request.getHeaders().getFirst("X-Correlation-Id");
        Mono<WebGraphQlResponse> response = chain.next(request);

        if (correlationId == null || correlationId.isBlank()) {
            return response;
        }

        return response.contextWrite(context ->
                context.put("correlationId", correlationId));
    }
}
```

Reactive service có thể đọc giá trị trong subscription:

```java
public Mono<Book> findBook(Long id) {
    return Mono.deferContextual(contextView -> {
        String correlationId = contextView.getOrDefault("correlationId", "unknown");
        return bookRepository.findById(id)
                .doOnNext(book -> log.debug("Loaded book, request={}", correlationId));
    });
}
```

Nếu resolver chỉ cần đọc metadata như tenant hoặc locale từ GraphQL execution, `GraphQLContext`/`@ContextValue` thường đơn giản hơn. Dùng Reactor Context khi một reactive pipeline hoặc thư viện downstream cần truy cập metadata trong suốt các operator.

## 14. Context propagation trong Spring MVC

Trong Spring MVC, GraphQL Java có thể gọi data fetcher trên thread khác với thread servlet ban đầu, ví dụ khi resolver trả `CompletableFuture` hoặc interceptor chuyển execution sang thread khác.

Spring for GraphQL hỗ trợ propagate `ThreadLocal` từ request thread tới các thread GraphQL gọi. Để một `ThreadLocal` tùy chỉnh được truyền, triển khai `io.micrometer.context.ThreadLocalAccessor`:

```java
public class TenantContextAccessor implements ThreadLocalAccessor<TenantContext> {

    @Override
    public Object key() {
        return TenantContextAccessor.class.getName();
    }

    @Override
    public TenantContext getValue() {
        return TenantContextHolder.get();
    }

    @Override
    public void setValue(TenantContext value) {
        TenantContextHolder.set(value);
    }

    @Override
    public void reset() {
        TenantContextHolder.clear();
    }
}
```

Đăng ký accessor khi khởi động:

```java
ContextRegistry.getInstance()
        .registerThreadLocalAccessor(new TenantContextAccessor());
```

Cũng có thể đăng ký accessor qua `ServiceLoader`. Accessor phải reset giá trị sau khi snapshot được khôi phục để tránh rò rỉ dữ liệu giữa các request dùng chung thread.

Nếu có thể, hãy truyền dữ liệu qua GraphQLContext một cách tường minh. `ThreadLocal` nên dành cho thư viện legacy hoặc thành phần buộc phải dùng request context kiểu imperative.

## 15. GraphQlContextAccessor và Micrometer Context Propagation

Spring for GraphQL cung cấp `GraphQlContextAccessor`, một `ContextAccessor` cho Micrometer Context Propagation để đọc và ghi giá trị giữa GraphQLContext và các context được quản lý bởi Micrometer.

Accessor này được tự động đăng ký qua `ServiceLoader`. Nhờ đó, context propagation có thể chuyển các giá trị giữa GraphQLContext, Reactor Context và ThreadLocal khi có accessor tương ứng.

Spring for GraphQL cũng có `ContextPropagationHelper` để hỗ trợ capture/propagate context và cancellation liên quan tới GraphQL execution. Nếu cần tùy biến mức thấp, hãy dùng API của phiên bản Spring GraphQL đang chạy; không sao chép mã từ một phiên bản snapshot sang ứng dụng đang dùng phiên bản cũ hơn.

## 16. Context và Spring Security

GraphQLContext không phải nơi thay thế Spring Security. Spring for GraphQL có thể inject `Principal` hoặc `@AuthenticationPrincipal` vào annotated controller khi Spring Security context hiện diện:

```java
@QueryMapping
public List<Order> myOrders(Principal principal) {
    return orderService.findByOwner(principal.getName());
}
```

Nếu resolver cần thêm tenant hoặc policy đã được xác thực, có thể đưa một actor snapshot vào GraphQLContext từ security layer:

```java
public record RequestActor(String userId, String tenantId) {
}
```

Sau khi authentication và tenant membership được xác minh, interceptor hoặc integration layer đặt `RequestActor` vào context. Resolver đọc snapshot này để gọi service.

Không lấy `userId`, `role` hoặc `tenantId` từ header do client gửi rồi xem đó là identity đã xác thực. Không đưa raw bearer token vào context nếu resolver chỉ cần user ID hoặc claims đã được kiểm tra. Hãy giữ thông tin tối thiểu cần thiết và vẫn thực hiện authorization tại service/domain boundary.

## 17. GraphQLContext trong WebSocket

GraphQL over WebSocket có vòng đời dài hơn HTTP request. Một connection có thể mang nhiều query, mutation và subscription. Vì vậy, cần phân biệt metadata ở cấp connection với metadata ở cấp từng GraphQL operation.

`WebSocketGraphQlInterceptor` mở rộng `WebGraphQlInterceptor` và có callback cho lúc connection bắt đầu/kết thúc, ngoài việc intercept từng request trên connection. Spring cung cấp `AuthenticationWebSocketInterceptor` cho WebMVC và WebFlux để lấy thông tin authentication từ thông điệp `connection_init` và propagate `SecurityContext` tới các operation sau đó.

Các nguyên tắc:

- Authentication có thể gắn với connection, nhưng GraphQLContext vẫn nên được chuẩn bị riêng cho từng operation.
- Không giữ một GraphQLContext mutable dùng chung cho mọi operation trên socket.
- Xử lý cancellation và cleanup khi subscription kết thúc hoặc connection đóng.
- Kiểm tra quyền lại khi policy hoặc trạng thái user có thể thay đổi trong thời gian connection tồn tại.
- Trong một interceptor chain, tối đa một interceptor có kiểu `WebSocketGraphQlInterceptor`.

## 18. Context với RSocket

Nếu ứng dụng dùng GraphQL over RSocket, Spring cung cấp `RSocketQlInterceptor` tương tự `WebGraphQlInterceptor`. Interceptor có thể tùy chỉnh `ExecutionInput` trước khi GraphQL Java chạy và xử lý `ExecutionResult` sau đó.

Không giả định `WebGraphQlInterceptor` được gọi cho RSocket. Hãy dùng interceptor đúng transport và đặt logic dùng chung vào một service/helper để tránh triển khai khác nhau giữa HTTP, WebSocket và RSocket.

## 19. GraphQLContext trong Instrumentation

GraphQL Java `Instrumentation` có thể đọc context khi execution bắt đầu. Điều này hữu ích cho metadata hoặc tùy chọn điều khiển GraphQL engine.

Ví dụ ghi thời điểm bắt đầu execution:

```java
public class ExecutionMetadataInstrumentation extends SimplePerformantInstrumentation {

    @Override
    public InstrumentationContext<ExecutionResult> beginExecution(
            InstrumentationExecutionParameters parameters,
            InstrumentationState state) {

        parameters.getGraphQLContext().put("executionStartedAt", Instant.now());
        return SimpleInstrumentationContext.noOp();
    }
}
```

Spring Boot có thể phát hiện `Instrumentation` bean và thêm vào `GraphQlSource`. Instrumentation phù hợp với logic ở cấp GraphQL engine như đo thời gian, gắn metadata execution hoặc thiết lập option cho subscription. Nó không thay thế interceptor khi cần đọc HTTP header, cookie hoặc thông tin của transport.

## 20. Trả dữ liệu từ context ra HTTP response

Context không tự động được serialize thành response. Nếu cần dùng một giá trị do resolver thêm vào context để cập nhật HTTP response, interceptor có thể đọc context sau khi execution hoàn tất:

```java
public class ResponseMetadataInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        return chain.next(request).doOnNext(response -> {
            GraphQLContext context = response.getExecutionInput().getGraphQLContext();
            String requestTag = context.get("responseTag");
            if (requestTag != null) {
                response.getResponseHeaders().add("X-Request-Tag", requestTag);
            }
        });
    }
}
```

Ví dụ minh họa việc interceptor đọc giá trị mà resolver đã ghi vào context. Chỉ đưa ra response header những metadata được phép công khai. Không phản chiếu access token, tenant secret hoặc thông tin nội bộ ra client.

## 21. Quy ước đặt key và kiểu dữ liệu

Khi có nhiều interceptor, controller và batch loader cùng ghi context, cần tránh trùng tên key:

```java
public final class GraphQlContextKeys {

    public static final String CORRELATION_ID = "app.correlationId";
    public static final String REQUEST_ACTOR = "app.requestActor";
    public static final String REQUEST_LOCALE = "app.requestLocale";

    private GraphQlContextKeys() {
    }
}
```

Dùng value object có kiểu rõ ràng thay vì đặt nhiều field rời rạc:

```java
public record RequestMetadata(
        String correlationId,
        Locale locale,
        RequestActor actor) {
}
```

Context có thể chứa object bất kỳ, nhưng object nên bất biến, có vòng đời phù hợp một execution và không giữ reference tới request/response object lớn sau khi request kết thúc.

## 22. Những lỗi thường gặp

- **Dùng GraphQLContext như biến global:** dữ liệu của request này có thể rò rỉ sang request khác.
- **Đặt `null` vào context:** GraphQLContext yêu cầu key và value khác null.
- **Dùng header làm identity:** client có thể tự giả mạo tenant hoặc user nếu header chưa được xác thực.
- **Nhầm context với GraphQL argument:** context là metadata nội bộ, argument là input theo schema.
- **Dùng main context cho dữ liệu chỉ thuộc một nhánh:** có thể gây va chạm giữa parent field; local context phù hợp hơn.
- **Dùng local context cho dữ liệu toàn request:** các resolver ở nhánh khác sẽ không nhìn thấy giá trị đó.
- **Nhầm Reactor Context với GraphQLContext:** hai cấu trúc có vòng đời và API truy cập khác nhau.
- **Dựa vào ThreadLocal trong WebFlux:** thread có thể đổi giữa các operator; dùng Reactor Context hoặc GraphQLContext.
- **Không reset ThreadLocal:** có nguy cơ rò rỉ metadata giữa các request dùng chung thread.
- **Tự đăng ký DataLoader toàn cục:** loader có thể chia sẻ cache và context giữa executions; dùng `BatchLoaderRegistry`.
- **Dùng context mutable từ nhiều resolver song song:** có thể tạo race condition trong object value.
- **Đưa raw token hoặc dữ liệu nhạy cảm vào context:** tăng phạm vi rò rỉ khi log hoặc debug.
- **Dùng WebGraphQlInterceptor cho RSocket:** interceptor không thuộc transport đó.
- **Test trực tiếp resolver rồi kết luận interceptor hoạt động:** test cần đi qua `WebGraphQlHandler` để chạy interceptor chain.

## 23. Kiểm thử GraphQLContext

Khi context được thêm bởi `WebGraphQlInterceptor`, hãy kiểm thử qua `WebGraphQlTester` để request đi qua đúng interceptor chain:

```java
WebGraphQlTester tester = WebGraphQlTester.builder(webGraphQlHandler)
        .headers(headers -> headers.set("X-Correlation-Id", "test-request-42"))
        .build();

tester.document("""
        query {
            requestMetadata
        }
        """)
    .execute()
    .path("requestMetadata")
    .entity(String.class)
    .isEqualTo("test-request-42");
```

Ví dụ giả định schema có field `requestMetadata` trả giá trị correlation ID từ `@ContextValue`. Có thể dùng `WebGraphQlTester.create(webGraphQlHandler)` nếu không cần tùy chỉnh header.

Nếu test trực tiếp `ExecutionGraphQlService`, web interceptor chain không chạy. Với cách test đó, hãy cấu hình `ExecutionInput` hoặc context theo builder của `ExecutionGraphQlServiceTester`.

Các tình huống nên kiểm thử:

1. Header metadata được đưa vào GraphQLContext.
2. `@ContextValue` và tham số `GraphQLContext` đọc được cùng giá trị.
3. Key bắt buộc bị thiếu sẽ tạo lỗi rõ ràng.
4. Key tùy chọn không có vẫn xử lý được bằng `Optional` hoặc `required = false`.
5. Hai request có correlation ID khác nhau không dùng nhầm context của nhau.
6. Local context chỉ xuất hiện ở nhánh con tương ứng.
7. Batch loader nhận đúng tenant từ main GraphQLContext.
8. Resolver reactive đọc được Reactor Context khi chạy qua WebFlux.
9. ThreadLocal accessor được reset sau execution.
10. WebSocket operation dùng đúng authentication context.
11. Header không tin cậy không thể thay đổi tenant hoặc principal.
12. Context không xuất hiện trong response trừ khi server chủ động đưa ra header/extension.

## 24. Quy trình thiết kế GraphQLContext

Khi cần truyền metadata qua nhiều resolver, hãy thực hiện:

1. Xác định giá trị nào thực sự dùng chung toàn execution.
2. Phân biệt metadata nội bộ với GraphQL variables/arguments.
3. Xác thực nguồn dữ liệu trước khi đưa tenant, actor hoặc policy vào context.
4. Tạo `GraphQLContext` theo từng `ExecutionInput` hoặc trong `WebGraphQlInterceptor`.
5. Dùng key có namespace và value object có kiểu rõ ràng.
6. Đọc giá trị qua `GraphQLContext`, `DataFetchingEnvironment` hoặc `@ContextValue`.
7. Dùng local context qua `DataFetcherResult` nếu dữ liệu chỉ thuộc một nhánh.
8. Dùng `BatchLoaderRegistry` để batch loader nhận context và context propagation.
9. Dùng Reactor Context cho reactive pipeline và ThreadLocalAccessor cho legacy MVC ThreadLocal.
10. Xử lý riêng connection-level và operation-level metadata với WebSocket.
11. Kiểm thử qua đúng tầng transport/interceptor.
12. Tránh giữ dữ liệu nhạy cảm hoặc object mutable không cần thiết trong context.

`GraphQLContext` là nơi chia sẻ metadata trong phạm vi một GraphQL execution. Spring for GraphQL cho phép bổ sung dữ liệu qua `WebGraphQlInterceptor`, đọc bằng `@ContextValue` hoặc `GraphQLContext`, và truyền dữ liệu riêng xuống nhánh con bằng local context. Khi dùng WebFlux, MVC, DataLoader, WebSocket hoặc RSocket, cần hiểu cơ chế context propagation của từng lớp. Thiết kế context theo request, xác thực nguồn dữ liệu và kiểm thử request isolation giúp resolver dùng chung metadata một cách an toàn.

## Tài liệu tham khảo

- [Spring for GraphQL — Server Transports and WebGraphQlInterceptor](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Request Execution and Context Propagation](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers: Context and Local Context](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL 1.4.1 — @ContextValue API](https://docs.spring.io/spring-graphql/docs/1.4.1/api/org/springframework/graphql/data/method/annotation/ContextValue.html)
- [Spring for GraphQL 1.4.6 — WebGraphQlInterceptor API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/server/WebGraphQlInterceptor.html)
- [Spring for GraphQL 1.4.3 — GraphQlContextAccessor API](https://docs.spring.io/spring-graphql/docs/1.4.3/api/org/springframework/graphql/execution/GraphQlContextAccessor.html)
- [GraphQL Java — ExecutionInput.Builder API](https://javadoc.io/doc/com.graphql-java/graphql-java/23.1/graphql/ExecutionInput.Builder.html)
- [GraphQL Java — GraphQLContext API](https://javadoc.io/doc/com.graphql-java/graphql-java/22.4/graphql/GraphQLContext.html)
