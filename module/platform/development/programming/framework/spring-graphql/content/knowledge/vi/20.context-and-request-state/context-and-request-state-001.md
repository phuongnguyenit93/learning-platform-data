# GraphQLContext

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của `GraphQLContext` trong một lần thực thi GraphQL.
- Phân biệt context cấp request với source object, field argument và local context.
- Đưa metadata từ HTTP request vào GraphQL execution bằng `WebGraphQlInterceptor`.
- Đọc context trong annotated controller bằng `@ContextValue` hoặc `GraphQLContext`.
- Dùng local context để truyền dữ liệu trong một nhánh của cây query.
- Truyền context tới DataLoader và batch loader.
- Phân biệt `GraphQLContext`, Reactor `Context` và `ThreadLocal`.
- Kết hợp GraphQL context với Spring Security mà không biến dữ liệu do client gửi thành danh tính đáng tin cậy.
- Giữ request state tách biệt giữa các GraphQL request đồng thời.

## 1. GraphQLContext giải quyết vấn đề gì?

Một GraphQL operation có thể gọi nhiều resolver. Các resolver này thường cần một số metadata chung như:

- Người dùng đã được xác thực.
- Tenant hoặc tổ chức đang hoạt động.
- Correlation ID để liên kết log giữa nhiều service.
- Locale hoặc tùy chọn định dạng.
- Feature flag hoặc thông tin phục vụ tracing.
- Chính sách truy cập đã được xác định ở tầng bảo mật.

Nếu truyền các giá trị này qua argument của từng field, schema sẽ bị trộn lẫn giữa dữ liệu nghiệp vụ và metadata của request. Nếu lưu chúng trong field mutable của controller singleton, các request đồng thời có nguy cơ dùng nhầm dữ liệu của nhau.

`GraphQLContext` cung cấp một vùng dữ liệu dùng chung trong phạm vi một lần thực thi GraphQL. Các DataFetcher trong cùng execution có thể đọc context này mà không cần thêm argument vào schema.

Ví dụ, một query có thể lấy thông tin người dùng, đơn hàng và lịch sử giao dịch. Các resolver có thể cùng cần `tenantId` và `correlationId`, dù hai giá trị này không phải input do client khai báo trong SDL.

## 2. GraphQLContext nằm ở đâu trong vòng đời request?

Với HTTP hoặc WebSocket, Spring for GraphQL cho phép chặn request trước khi gọi GraphQL Java thông qua `WebGraphQlInterceptor`. Interceptor có thể đọc thông tin transport, bổ sung dữ liệu vào `ExecutionInput`, rồi chuyển request cho interceptor tiếp theo và GraphQL engine.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[HTTP hoặc WebSocket request] --> B[WebGraphQlInterceptor]
    B --> C[Đọc header và metadata]
    C --> D[Thêm GraphQLContext vào ExecutionInput]
    D --> E[ExecutionGraphQlService]
    E --> F[GraphQL Java engine]
    F --> G[Query / Mutation / Subscription resolvers]
    G --> H[Response]
~~~

`GraphQLContext` được gắn với một GraphQL execution. Nó không phải một object toàn cục của ứng dụng và không nên được lưu trong singleton để dùng lại giữa các request.

Một request WebSocket có thể mang nhiều operation theo thời gian. Mỗi operation vẫn có execution context riêng; trạng thái xác thực ở cấp kết nối cần được chuyển vào từng request theo cơ chế WebSocket interceptor phù hợp.

## 3. Đưa dữ liệu vào GraphQLContext bằng WebGraphQlInterceptor

`WebGraphQlInterceptor` cho phép đọc thông tin HTTP request và tùy chỉnh `ExecutionInput` trước khi GraphQL Java thực thi operation.

Ví dụ, tạo hoặc tiếp nhận correlation ID từ HTTP header:

~~~java
import java.util.UUID;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class CorrelationIdInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String correlationId =
                request.getHeaders().getFirst("X-Correlation-Id");

        if (correlationId == null || correlationId.isBlank()) {
            correlationId = UUID.randomUUID().toString();
        }

        String value = correlationId;

        request.configureExecutionInput((executionInput, builder) ->
                builder.graphQLContext(context ->
                        context.put("correlationId", value)
                ).build()
        );

        return chain.next(request);
    }
}
~~~

Các bước:

1. Interceptor nhận `WebGraphQlRequest`.
2. Đọc header `X-Correlation-Id`.
3. Tạo ID mới nếu client không gửi.
4. Dùng `configureExecutionInput` để thêm giá trị vào `GraphQLContext`.
5. Gọi `chain.next(request)` để tiếp tục xử lý.

`correlationId` là metadata phục vụ tracing. Nếu client tự gửi header này, server có thể dùng nó làm nhãn tương quan sau khi áp dụng quy tắc kiểm tra độ dài và ký tự phù hợp. Không dùng một header tùy ý như `X-User-Id` làm bằng chứng xác thực người dùng.

Nếu có nhiều interceptor cùng bổ sung metadata, hãy thống nhất key và cách kết hợp các giá trị để interceptor sau không vô tình ghi đè dữ liệu mà interceptor trước đã thêm.

Nếu ứng dụng chỉ cần chuyển một số HTTP header vào context, Spring for GraphQL còn có `HttpRequestHeaderInterceptor`:

~~~java
@Configuration
public class GraphQlInterceptorConfiguration {

    @Bean
    HttpRequestHeaderInterceptor requestHeaderInterceptor() {
        return HttpRequestHeaderInterceptor.builder()
                .mapHeader("X-Request-Locale")
                .build();
    }
}
~~~

Header được ánh xạ vào GraphQL context để controller có thể đọc bằng `@ContextValue`. Chỉ nên ánh xạ những header thực sự cần thiết; không nên sao chép toàn bộ header vào context.

## 4. Đọc context bằng @ContextValue

Trong annotated controller, `@ContextValue` lấy một giá trị theo key từ GraphQLContext của execution.

SDL không cần khai báo argument `correlationId`:

~~~graphql
type Query {
  requestId: String!
}
~~~

Controller:

~~~java
@Controller
public class RequestMetadataController {

    @QueryMapping
    public String requestId(
            @ContextValue("correlationId") String correlationId) {

        return correlationId;
    }
}
~~~

Client chỉ cần gọi:

~~~graphql
query {
  requestId
}
~~~

Resolver nhận `correlationId` từ context đã được interceptor chuẩn bị. Client không thể tự thay đổi giá trị bằng cách thêm một GraphQL argument cùng tên, vì đây là hai nguồn dữ liệu khác nhau.

Dùng `@ContextValue` khi method chỉ cần một hoặc một vài key cụ thể. Cách này làm chữ ký method rõ ràng và không buộc resolver phụ thuộc vào toàn bộ cấu trúc context.

## 5. Nhận toàn bộ GraphQLContext trong controller

Nếu method cần nhiều giá trị hoặc cần đọc/ghi context, có thể nhận trực tiếp `graphql.GraphQLContext` làm tham số.

~~~java
import graphql.GraphQLContext;

@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @QueryMapping
    public List<Order> orders(GraphQLContext context) {
        String tenantId = context.get("tenantId");
        String correlationId = context.get("correlationId");

        return orderService.findByTenant(tenantId, correlationId);
    }
}
~~~

Trong ví dụ này, `tenantId` và `correlationId` được đưa vào context trước khi resolver chạy. Service nhận các giá trị đó để truy vấn và ghi log.

Có thể dùng `DataFetchingEnvironment` nếu cần truy cập context cùng nhiều metadata khác:

~~~java
@QueryMapping
public List<Order> orders(DataFetchingEnvironment environment) {
    GraphQLContext context = environment.getGraphQlContext();
    String tenantId = context.get("tenantId");

    return orderService.findByTenant(tenantId);
}
~~~

Với controller thông thường, `@ContextValue` hoặc tham số `GraphQLContext` thường dễ đọc hơn việc nhận toàn bộ `DataFetchingEnvironment`.

## 6. GraphQLContext khác source object và argument

Các giá trị này đều có thể xuất hiện trong một resolver nhưng mang ý nghĩa khác nhau:

| Thành phần | Nguồn | Phạm vi | Ví dụ |
|---|---|---|---|
| Source object | Kết quả field cha | Một nhánh trong cây query | `Book` đang được phân giải |
| `@Argument` | Input của field hiện tại do client gửi | Một field | `first = 10` |
| `GraphQLContext` | Transport interceptor hoặc execution setup | Toàn GraphQL execution | `correlationId`, `tenantId` |
| Local context | Field cha chủ động truyền xuống | Một nhánh con | Author đã tải sẵn cho Book |
| Reactor Context | Reactive pipeline | Một chuỗi reactive | Trace metadata trong WebFlux |

Ví dụ kết hợp source, argument và context:

~~~graphql
type Book {
  id: ID!
  reviews(first: Int): [Review!]!
}
~~~

~~~java
@SchemaMapping
public List<Review> reviews(
        Book book,
        @Argument Integer first,
        @ContextValue("tenantId") String tenantId) {

    return reviewService.findByBook(
            book.getId(), first, tenantId);
}
~~~

- `Book book` là source object được trả về từ field cha.
- `first` là argument của field `Book.reviews`.
- `tenantId` là metadata chung của GraphQL execution.

Không đưa dữ liệu thuộc argument vào GraphQLContext chỉ để tránh khai báo SDL. Argument mô tả input của một field; context mô tả metadata xuyên suốt execution.

## 7. Dùng local context cho một nhánh query

GraphQLContext chính được chia sẻ cho toàn execution. Đôi khi field cha đã tải sẵn dữ liệu mà chỉ các field con của object đó cần dùng. Đưa dữ liệu riêng của một nhánh vào context toàn cục sẽ làm context trở nên khó hiểu và có thể tạo xung đột key.

GraphQL Java cung cấp local context. Spring for GraphQL cho phép controller trả về `DataFetcherResult<T>` để truyền object kết quả cùng local context cho các field con.

Ví dụ, khi tải Book, service cũng đã tải Author:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public DataFetcherResult<Book> book(@Argument Long id) {
        BookAndAuthor result = bookService.findBookAndAuthor(id);

        GraphQLContext localContext = GraphQLContext.getDefault()
                .put("prefetchedAuthor", result.author());

        return DataFetcherResult.<Book>newResult()
                .data(result.book())
                .localContext(localContext)
                .build();
    }

    @SchemaMapping
    public Author author(
            Book book,
            @LocalContextValue("prefetchedAuthor") Author author) {
        return author;
    }
}
~~~

Ở đây:

- Giá trị `data` là source object Book cho field con.
- `localContext` mang Author đã được tải sẵn.
- `@LocalContextValue` đọc dữ liệu từ local context của nhánh hiện tại.

Local context được truyền xuống các field con thuộc nhánh đó. Một field khác trong nhánh Query không tự động nhìn thấy giá trị này.

Dùng local context khi dữ liệu có phạm vi hẹp và đã được field cha chuẩn bị. Nếu dữ liệu cần dùng xuyên nhiều field độc lập hoặc nhiều nhánh của operation, hãy cân nhắc GraphQLContext hoặc DataLoader phù hợp.

## 8. Phân biệt @ContextValue và @LocalContextValue

Hai annotation có tên gần giống nhau nhưng đọc từ hai vùng context khác nhau:

| Annotation | Nguồn | Phạm vi |
|---|---|---|
| `@ContextValue` | GraphQLContext chính | Toàn execution |
| `@LocalContextValue` | Local GraphQLContext | Nhánh được field cha truyền xuống |

Ví dụ:

~~~java
@SchemaMapping
public List<Book> relatedBooks(
        Book book,
        @ContextValue("tenantId") String tenantId,
        @LocalContextValue("prefetchedAuthor") Author author) {

    return bookService.findRelated(
            book.getId(), tenantId, author.id());
}
~~~

Resolver nhận:

- `tenantId` từ context chính, dùng chung cho toàn execution.
- `author` từ local context do parent field truyền xuống.

Nếu key không có trong đúng vùng context, việc bind tham số có thể thất bại hoặc không có giá trị như mong muốn tùy cấu hình. Hãy bảo đảm field cha luôn tạo local context khi field con yêu cầu nó.

## 9. GraphQLContext và DataLoader

Spring for GraphQL tích hợp `BatchLoaderRegistry` với GraphQLContext của execution. Batch loader có thể nhận `BatchLoaderEnvironment` và đọc cùng context mà DataFetcher hoặc annotated controller sử dụng.

Ví dụ, một ứng dụng multi-tenant cần tải Author theo ID và tenant:

~~~java
@Component
public class AuthorBatchLoader {

    public AuthorBatchLoader(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) -> {
                    GraphQLContext context = environment.getContext();
                    String tenantId = context.get("tenantId");

                    return authorService
                            .findAllByIdsAndTenant(authorIds, tenantId)
                            .collectMap(Author::id);
                });
    }
}
~~~

Resolver sử dụng DataLoader:

~~~java
@SchemaMapping
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorLoader) {

    return authorLoader.load(book.authorId());
}
~~~

Batch loader nhận một tập ID và tenant hiện tại từ context, sau đó chỉ tải dữ liệu trong tenant đó. Đây là cách giữ điều kiện phân vùng dữ liệu nhất quán giữa các field resolver.

Spring đăng ký DataLoader theo từng GraphQL request. Không tự tạo một DataLoader singleton dùng chung giữa các request, vì cache của DataLoader có thể chứa dữ liệu của request trước.

Với local context được truyền cho từng lần gọi DataLoader, `BatchLoaderEnvironment` còn cung cấp `keyContexts` để truy cập local context tương ứng với từng key. Điều này hữu ích khi mỗi parent object có metadata riêng mà batch loader cần giữ đúng quan hệ.

## 10. GraphQLContext không thay thế Spring Security

GraphQLContext là nơi truyền metadata tới DataFetcher. Nó không tự xác thực người dùng và cũng không tự thực thi authorization.

Không nên lấy một header hoặc argument do client tự gửi rồi xem đó là danh tính đã được xác thực:

~~~java
// Không dùng giá trị client tự gửi làm danh tính tin cậy.
@QueryMapping
public List<Order> orders(@Argument String userId) {
    return orderService.findByUserId(userId);
}
~~~

Nếu client có thể truyền bất kỳ `userId` nào, họ có thể thử truy cập dữ liệu của người khác nếu service không kiểm tra quyền.

Với Spring Security, controller có thể nhận `Principal` hoặc `@AuthenticationPrincipal` từ SecurityContext:

~~~java
@QueryMapping
public List<Order> myOrders(Principal principal) {
    return orderService.findVisibleTo(principal.getName());
}
~~~

Có thể dùng method security hoặc kiểm tra quyền trong service để bảo vệ dữ liệu. GraphQLContext vẫn có thể mang tenant ID đã được xác minh, correlation ID hoặc chính sách đã được xác định từ danh tính xác thực.

Nguyên tắc:

- Xác thực ở tầng Spring Security hoặc cơ chế authentication phù hợp.
- Dùng Principal hoặc Authentication để lấy danh tính đáng tin cậy.
- Chỉ đưa thông tin đã được xác minh vào context.
- Kiểm tra quyền ở service hoặc field resolver theo yêu cầu nghiệp vụ.
- Không coi việc một key tồn tại trong GraphQLContext là bằng chứng người dùng được phép truy cập dữ liệu.

## 11. Context với WebSocket và Subscription

Với GraphQL qua WebSocket, một kết nối có thể tồn tại lâu và mang nhiều operation. `WebSocketGraphQlInterceptor` mở rộng `WebGraphQlInterceptor`, hỗ trợ xử lý vòng đời kết nối và các request GraphQL trên kết nối đó.

Spring for GraphQL có các `AuthenticationWebSocketInterceptor` tích hợp cho Spring MVC và WebFlux. Chúng hỗ trợ lấy thông tin xác thực từ payload `connection_init`, xác thực và truyền `SecurityContext` tới các request tiếp theo trên kết nối.

Cần phân biệt:

- Trạng thái kết nối WebSocket: thông tin gắn với kết nối và vòng đời kết nối.
- GraphQLContext: metadata của một lần thực thi GraphQL.
- Subscription publisher: luồng event tồn tại cho đến khi hoàn tất hoặc bị hủy.

Không nên giả định một object GraphQLContext có thể được giữ làm session toàn cục cho toàn bộ kết nối. Cơ chế WebSocket interceptor chịu trách nhiệm chuyển trạng thái xác thực cần thiết sang từng request. Với subscription dài hạn, cần cân nhắc token hết hạn, thu hồi quyền và hủy subscription khi danh tính không còn hợp lệ.

## 12. GraphQLContext và Reactor Context

Hai loại context này không thay thế nhau.

`GraphQLContext` là context tường minh của GraphQL execution, được truyền tới DataFetcher và controller. `Reactor Context` là context gắn với reactive subscriber chain, thường dùng trong WebFlux để truyền metadata xuyên qua các toán tử reactive.

Spring for GraphQL hỗ trợ propagate Reactor Context từ WebFlux request handling chain tới reactive DataFetcher. Ví dụ, một interceptor có thể thêm metadata vào Reactor Context:

~~~java
@Component
public class TraceReactorContextInterceptor
        implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String traceMarker = "graphql-request";

        return chain.next(request)
                .contextWrite(context ->
                        context.put("traceMarker", traceMarker));
    }
}
~~~

Reactive service có thể đọc giá trị trong pipeline:

~~~java
public Mono<Book> findBook(String id) {
    return Mono.deferContextual(contextView -> {
        String traceMarker = contextView.get("traceMarker");
        return repository.findById(id)
                .doOnNext(book -> log.debug(
                        "Loaded book for {}", traceMarker));
    });
}
~~~

Ví dụ này minh họa metadata của reactive chain. Nếu controller cần truy cập dữ liệu theo key một cách tường minh, GraphQLContext và `@ContextValue` thường dễ hiểu hơn.

Với Spring MVC, context có thể dựa trên `ThreadLocal`. Do GraphQL Java có thể thực thi DataFetcher trên thread khác thread xử lý HTTP ban đầu, việc truyền ThreadLocal cần cơ chế context propagation. Spring for GraphQL hỗ trợ Micrometer Context Propagation thông qua `ThreadLocalAccessor` do ứng dụng đăng ký.

Không dùng ThreadLocal làm kho request state mặc định trong reactive pipeline. Thread có thể thay đổi giữa các bước xử lý, khiến dữ liệu không được truyền như mong đợi.

## 13. Giữ request state an toàn khi có nhiều request đồng thời

Một ứng dụng Spring thường dùng singleton controller và service. Nhiều GraphQL execution có thể chạy đồng thời, vì vậy state của từng request phải nằm trong đúng phạm vi.

Không nên làm như sau:

~~~java
@Controller
public class UnsafeOrderController {

    private String currentTenantId;

    @QueryMapping
    public List<Order> orders(
            @ContextValue("tenantId") String tenantId) {

        this.currentTenantId = tenantId;
        return orderService.findByTenant(this.currentTenantId);
    }
}
~~~

Hai request từ hai tenant có thể ghi đè `currentTenantId` của nhau. Kết quả là truy vấn có thể dùng nhầm tenant.

Hãy truyền giá trị qua tham số method hoặc context của execution:

~~~java
@Controller
public class OrderController {

    @QueryMapping
    public List<Order> orders(
            @ContextValue("tenantId") String tenantId) {

        return orderService.findByTenant(tenantId);
    }
}
~~~

Một số quy tắc:

- Không lưu user, tenant hoặc correlation ID của request vào field mutable singleton.
- Không dùng static mutable Map để giữ metadata request.
- Không chia sẻ DataLoader hoặc cache request-scoped giữa các execution.
- Ưu tiên tạo context trước khi GraphQL engine chạy.
- Đưa các object bất biến hoặc có vòng đời rõ ràng vào context.
- Không lưu payload lớn hoặc entity graph lớn nếu không cần thiết.
- Dùng local context khi dữ liệu chỉ phục vụ một nhánh.
- Dùng DataLoader cho cache và batch loading theo request thay vì tự xây cache dùng chung.

GraphQL Java mô tả GraphQLContext là thread-safe, nhưng điều đó không tự làm cho mọi object được đặt bên trong context trở nên thread-safe. Hãy ưu tiên dữ liệu bất biến và tránh sửa context từ nhiều resolver không phối hợp.

GraphQL Java yêu cầu key và value được lưu trong `GraphQLContext` đều khác null. Nếu một giá trị không tồn tại, hãy bỏ qua key đó hoặc dùng một kiểu wrapper không null và xử lý trạng thái vắng mặt rõ ràng; không gọi `put(key, null)`.

## 14. Kiểm thử GraphQLContext

Nên kiểm thử cả bước interceptor đưa metadata vào context và resolver đọc đúng giá trị đó.

Ví dụ SDL:

~~~graphql
type Query {
  requestId: String!
}
~~~

Controller:

~~~java
@Controller
public class RequestIdController {

    @QueryMapping
    public String requestId(
            @ContextValue("correlationId") String correlationId) {
        return correlationId;
    }
}
~~~

Với `WebGraphQlTester`, có thể gửi header để kiểm tra interceptor:

Ví dụ giả định tester được tạo từ `WebGraphQlHandler` đã đăng ký interceptor ở phần trước. Nếu kiểm thử qua HTTP endpoint thật hoặc test client, có thể dùng `HttpGraphQlTester` với `WebTestClient` và cấu hình cùng header.

~~~java
class RequestContextTests {

    @Autowired
    WebGraphQlTester webGraphQlTester;

    @Test
    void shouldExposeCorrelationIdToController() {
        WebGraphQlTester testerWithHeader = webGraphQlTester.mutate()
                .header("X-Correlation-Id", "test-correlation-01")
                .build();

        testerWithHeader.document("{ requestId }")
                .execute()
                .path("requestId")
                .entity(String.class)
                .isEqualTo("test-correlation-01");
    }
}
~~~

Các tình huống nên kiểm thử:

1. Header có giá trị được chuyển vào GraphQLContext.
2. Header không có giá trị thì interceptor tạo correlation ID.
3. Resolver đọc đúng context qua `@ContextValue`.
4. Resolver nhận toàn bộ GraphQLContext khi cần nhiều key.
5. Local context chỉ xuất hiện ở nhánh được field cha truyền xuống.
6. Batch loader nhận đúng tenant hoặc metadata từ GraphQLContext.
7. Hai request đồng thời không dùng nhầm context của nhau.
8. Principal phản ánh danh tính từ Spring Security.
9. Client không thể thay đổi tenant hoặc user đã xác thực bằng GraphQL argument.
10. Reactor Context được truyền qua reactive chain khi chạy trên WebFlux.

Test tích hợp qua transport hữu ích để xác nhận header/interceptor. Test resolver riêng có thể kiểm tra logic sử dụng context, nhưng không thay thế test đường đi từ transport tới GraphQL execution.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `@ContextValue` không tìm thấy key | Interceptor chưa thêm key hoặc sai tên | Kiểm tra key và thứ tự interceptor |
| Context bị null ở resolver | Giá trị không được thêm vào ExecutionInput | Kiểm tra `configureExecutionInput` |
| Request dùng nhầm tenant | Lưu tenant trong field mutable singleton | Truyền tenant qua GraphQLContext hoặc method argument |
| Local context không có ở field con | Parent resolver không trả `DataFetcherResult` với local context | Kiểm tra đường truyền local context |
| DataLoader không nhận tenant | Batch loader chưa đọc GraphQLContext | Dùng `BatchLoaderEnvironment.getContext()` |
| Reactor Context không có trong service | Code chạy ngoài reactive chain hoặc context chưa được propagate | Kiểm tra WebFlux chain và `contextWrite` |
| ThreadLocal mất dữ liệu | GraphQL DataFetcher chạy trên thread khác | Đăng ký `ThreadLocalAccessor` hoặc dùng context tường minh |
| Client truy cập dữ liệu tenant khác | Tin header/argument do client tự gửi | Xác thực và kiểm tra quyền ở server |
| WebSocket dùng thông tin xác thực cũ | Không xử lý token hết hạn hoặc thu hồi quyền | Kiểm tra authentication theo vòng đời kết nối và từng operation |

## 16. Nguyên tắc thiết kế context và request state

Khi triển khai GraphQLContext:

- Dùng context cho metadata xuyên suốt một GraphQL execution.
- Tạo context từ interceptor hoặc execution setup trước khi resolver chạy.
- Dùng `@ContextValue` khi chỉ cần một key.
- Nhận `GraphQLContext` khi cần nhiều key hoặc thao tác context.
- Dùng local context cho dữ liệu chỉ thuộc một nhánh query.
- Dùng `BatchLoaderEnvironment` để truy cập context trong batch loader.
- Dùng Principal hoặc Spring Security cho danh tính xác thực.
- Dùng Reactor Context cho metadata cần đi theo reactive chain.
- Dùng Micrometer Context Propagation nếu cần truyền ThreadLocal qua các thread trong Spring MVC.
- Không lưu request state trong singleton hoặc static mutable state.
- Ưu tiên dữ liệu bất biến, nhỏ gọn và có vòng đời rõ ràng.
- Kiểm thử request isolation, quyền truy cập và context propagation.

## Kết luận

`GraphQLContext` là vùng metadata dùng chung trong một lần thực thi GraphQL. Spring for GraphQL cho phép thêm dữ liệu vào context thông qua `WebGraphQlInterceptor`, sau đó truy cập từ controller bằng `@ContextValue`, tham số `GraphQLContext` hoặc từ `DataFetchingEnvironment`.

Local context phục vụ một nhánh của cây query; Reactor Context phục vụ reactive pipeline; Spring Security cung cấp danh tính và trạng thái xác thực. Phân biệt đúng các phạm vi này giúp truyền request state an toàn, tránh rò rỉ dữ liệu giữa request đồng thời và giữ schema tập trung vào hợp đồng nghiệp vụ.

## Tài liệu tham khảo

- [Spring for GraphQL — Server Transports and WebGraphQlInterceptor](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Annotated Controllers, Context and Local Context](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution and Context Propagation](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL Java — GraphQLContext API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/GraphQLContext.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
