# DataLoader context trong Spring for GraphQL

DataLoader gom nhiều lần tải dữ liệu thành một batch để giảm số truy vấn lặp lại, đặc biệt trong các field lồng nhau của GraphQL. Khi batch loader cần biết thông tin của request hiện tại, chẳng hạn tenant, locale hoặc principal đã xác thực, ta cần truyền context đến đúng batch loader.

Trong Spring for GraphQL, `BatchLoaderRegistry` đăng ký DataLoader theo kiểu key/value và quản lý việc tạo DataLoader cho từng GraphQL request. Context của request được truyền đến batch loader thông qua `BatchLoaderEnvironment`. Nhờ vậy, batch loader có thể dùng cùng metadata mà các resolver khác đang sử dụng, nhưng vẫn giữ dữ liệu request tách biệt giữa các lần thực thi.

## 1. Vì sao DataLoader cần context?

Giả sử query trả về nhiều sách, mỗi sách có một tác giả:

```graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

Resolver của field `Book.author` có thể dùng DataLoader để gom các `authorId` thành một lần tải theo batch. Nhưng trong ứng dụng đa tenant, chỉ có ID tác giả là chưa đủ. Batch loader còn cần biết tenant hiện tại để không lấy nhầm tác giả của tenant khác.

Các thông tin khác có thể cần trong batch loader:

- Tenant hoặc organization hiện tại để giới hạn dữ liệu.
- Principal hoặc thông tin quyền đã được xác thực để lọc bản ghi.
- Locale để chọn nội dung hoặc bản dịch phù hợp.
- Correlation ID hoặc trace metadata để ghi log và quan sát request.
- Feature flag hoặc cấu hình theo request đã được server xác minh.

Context giúp truyền các thông tin dùng chung này mà không phải thêm chúng vào mọi GraphQL argument hoặc nhét chúng vào key của DataLoader một cách tùy tiện.

## 2. Phân biệt GraphQLContext và DataLoader context

Có hai khái niệm liên quan nhưng khác vai trò:

| Khái niệm | Phạm vi | Nơi truy cập thường dùng |
| --- | --- | --- |
| `GraphQLContext` | Một GraphQL execution/request | `DataFetchingEnvironment.getGraphQlContext()`, `@ContextValue` |
| DataLoader batch context | Context được cung cấp cho lần batch dispatch của một DataLoader | `BatchLoaderEnvironment.getContext()` |
| Per-key context | Metadata gắn với một lần `load(key, keyContext)` cụ thể | `BatchLoaderEnvironment.getKeyContexts()` trong API GraphQL Java hỗ trợ |

`GraphQLContext` phù hợp để giữ metadata chung của request. Với DataLoader được đăng ký qua `BatchLoaderRegistry` của Spring for GraphQL, context GraphQL của request được truyền đến batch loader thông qua `BatchLoaderEnvironment`.

Per-key context có phạm vi nhỏ hơn: mỗi key được tải có thể đi kèm metadata riêng. Chỉ dùng khi cùng một batch thực sự chứa các key cần xử lý với thông tin khác nhau. Nếu tenant hoặc principal là chung cho toàn request, dùng GraphQLContext thường đơn giản và nhất quán hơn.

Không nhầm context với key. Key xác định dữ liệu cần tải, ví dụ `authorId`; context cung cấp môi trường thực thi, ví dụ `tenantId`. Nếu một yếu tố ảnh hưởng đến danh tính dữ liệu được cache, phải bảo đảm cache không trả kết quả sai khi yếu tố đó thay đổi.

## 3. Đưa request metadata vào GraphQLContext

Spring for GraphQL cho phép tùy biến `ExecutionInput` qua `WebGraphQlInterceptor`. Ví dụ, ứng dụng lấy tenant từ thông tin đã được xác thực và đưa tenant vào GraphQLContext:

```java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class TenantContextInterceptor implements WebGraphQlInterceptor {

    private final TenantResolver tenantResolver;

    public TenantContextInterceptor(TenantResolver tenantResolver) {
        this.tenantResolver = tenantResolver;
    }

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        String tenantId = tenantResolver.resolveAuthorizedTenant(request);

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context -> context.put("tenantId", tenantId))
                        .build());

        return chain.next(request);
    }
}
```

`TenantResolver` là thành phần của ứng dụng, chịu trách nhiệm lấy tenant từ principal/session/token đã xác thực và kiểm tra người dùng có quyền truy cập tenant đó. Không nên lấy một header tùy ý hoặc argument do client gửi rồi đưa thẳng vào context như một thông tin đáng tin cậy.

Interceptor chạy ở request layer trước khi GraphQL execution bắt đầu. Các resolver và batch loader trong cùng execution có thể dùng lại context này. Hãy dùng key thống nhất, ví dụ hằng số `TENANT_ID_CONTEXT_KEY`, để tránh lỗi do gõ sai tên key.

Nếu cần truyền principal hoặc locale, có thể đưa các giá trị đã được xác minh vào context theo cách tương tự. Chỉ lưu metadata thực sự cần thiết; tránh đưa token, mật khẩu hoặc object lớn không cần thiết vào GraphQLContext.

## 4. Đọc GraphQLContext trong resolver

Resolver có thể lấy context bằng `DataFetchingEnvironment` hoặc `@ContextValue`.

Ví dụ dùng `@ContextValue`:

```java
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(
            @ContextValue("tenantId") String tenantId) {
        return bookService.findBooksForTenant(tenantId);
    }
}
```

Hoặc đọc trực tiếp từ `DataFetchingEnvironment`:

```java
import graphql.schema.DataFetchingEnvironment;

@QueryMapping
public List<Book> books(DataFetchingEnvironment environment) {
    String tenantId = environment.getGraphQlContext().get("tenantId");
    return bookService.findBooksForTenant(tenantId);
}
```

`@ContextValue` phù hợp khi method chỉ cần một vài giá trị context cụ thể. `DataFetchingEnvironment` hữu ích khi cần nhiều metadata execution khác. Trong cả hai trường hợp, context được đọc theo request hiện tại; không lưu nó vào field mutable của controller singleton.

## 5. Đăng ký DataLoader bằng BatchLoaderRegistry

Spring for GraphQL khuyến khích đăng ký batch loader thông qua `BatchLoaderRegistry`. Registry tự đăng ký DataLoader vào GraphQL execution context cho từng request và hỗ trợ context propagation.

Ví dụ đăng ký mapped batch loader cho `Author`:

```java
import graphql.GraphQLContext;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class AuthorBatchLoader {

    public AuthorBatchLoader(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) -> {
                    GraphQLContext context =
                            (GraphQLContext) environment.getContext();
                    String tenantId = context.get("tenantId");

                    return authorService.findByTenantAndIds(tenantId, authorIds)
                            .collectMap(Author::id);
                });
    }
}
```

`registerMappedBatchLoader` nhận tập key và trả về map từ key sang kết quả. Trong ví dụ, `environment.getContext()` cung cấp context của lần batch; Spring for GraphQL truyền GraphQLContext của request vào đây khi dùng BatchLoaderRegistry mặc định. `authorService` trả về `Flux<Author>`, sau đó `collectMap(Author::id)` tạo `Mono<Map<Long, Author>>` theo dạng mà mapped loader cần.

Mapped loader thuận tiện vì không cần tự sắp xếp kết quả theo thứ tự của key đầu vào. Với mỗi key không tìm thấy bản ghi, map có thể không chứa key đó; DataLoader sẽ trả kết quả thiếu tương ứng theo contract của mapped loader. Nếu dùng positional batch loader, phải trả danh sách có đúng số phần tử và đúng thứ tự tương ứng với các key đầu vào.

Tên DataLoader được suy ra từ cặp kiểu key/value trong ví dụ. Nếu có nhiều loader cùng kiểu hoặc cần tên rõ ràng, có thể đăng ký theo tên và dùng cùng tên khi lấy DataLoader trong resolver.

## 6. Dùng DataLoader trong resolver field

Sau khi đăng ký loader cho cặp `Long` và `Author`, resolver có thể nhận `DataLoader` làm tham số:

```java
import java.util.concurrent.CompletableFuture;
import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookFieldController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorDataLoader) {
        return authorDataLoader.load(book.authorId());
    }
}
```

Resolver chỉ cung cấp `authorId` làm key. Tenant không cần được truyền vào từng lần `load`, vì batch loader đã nhận được tenant từ request context. Khi nhiều sách cùng được resolve trong một execution, DataLoader gom các author ID để batch loader tải theo lô.

Nếu resolver dùng `Mono` hoặc `Flux`, Spring for GraphQL hỗ trợ kiểu reactive trong quá trình hoàn tất field. Với DataLoader Java API, `load` thường trả `CompletableFuture`; có thể giữ nguyên future hoặc chuyển sang reactive type theo nhu cầu của resolver.

## 7. Context trong batch loader và GraphQLContext có cùng vòng đời request

Với cách tích hợp mặc định của Spring for GraphQL:

1. `WebGraphQlInterceptor` thêm metadata vào GraphQLContext trước execution.
2. Resolver đọc context bằng `@ContextValue` hoặc `DataFetchingEnvironment`.
3. `BatchLoaderRegistry` tạo/đăng ký DataLoader cho execution hiện tại.
4. Khi DataLoader dispatch batch, `BatchLoaderEnvironment` cung cấp context tương ứng.
5. Batch loader dùng context để lọc dữ liệu hoặc áp dụng chính sách theo request.

Điều này tránh phải truyền cùng một tenant ID qua từng GraphQL argument, từng resolver và từng key của DataLoader. Nó cũng giúp dữ liệu theo request không bị chia sẻ nhầm giữa hai người dùng.

Context không thay thế kiểm tra quyền. Nếu tenant ID được đưa vào context, phải chắc chắn giá trị đó đã được xác minh từ authentication/authorization layer. Batch loader vẫn nên gọi service/repository có giới hạn tenant và không truy vấn dữ liệu toàn cục rồi mới lọc ở Java nếu có thể giới hạn ngay tại database.

## 8. Khi nào dùng per-key context?

GraphQL Java hỗ trợ truyền context riêng cho từng lần load, bên cạnh context chung của batch. Điều này hữu ích khi mỗi key cần một metadata khác nhau, chẳng hạn:

- Mỗi key cần một locale khác nhau.
- Mỗi item cần một projection hoặc chế độ hiển thị riêng.
- Cần gắn tracing metadata riêng với từng lần load.

Với API hỗ trợ key context, caller có thể gọi `DataLoader.load(key, keyContext)`. Batch loader có thể đọc context theo key thông qua `BatchLoaderEnvironment.getKeyContexts()`.

Không dùng per-key context chỉ để truyền tenant nếu toàn bộ keys trong request cùng một tenant; GraphQLContext cấp request đơn giản hơn. Cũng cần nhớ rằng khi cùng một key được load nhiều lần với key context khác nhau, chính sách caching và hợp nhất load phải được xem xét cẩn thận. Nếu context làm thay đổi kết quả, cache key phải phân biệt các trường hợp hoặc phải tắt/điều chỉnh caching phù hợp.

## 9. Context ảnh hưởng đến DataLoader cache như thế nào?

DataLoader thường có cache theo key trong phạm vi một GraphQL request. Ví dụ key `authorId=10` được load hai lần trong cùng request có thể chỉ cần một lần batch load. Đây là cơ chế memoization giúp tránh tải trùng.

Nếu kết quả phụ thuộc vào context, cần bảo đảm cache scope và key phù hợp:

- Nếu tenant cố định trong toàn request và DataLoader được tạo riêng cho request, key `authorId` thường đủ vì mọi lần load dùng cùng tenant.
- Nếu cùng một DataLoader có thể xử lý nhiều tenant trong một execution, tenant phải trở thành một phần của key hoặc context/cache policy phải ngăn việc dùng chung kết quả sai.
- Nếu dùng cache bên ngoài request, phải đưa tenant/locale/authorization dimension vào cache key hoặc bảo đảm cache được phân vùng tương ứng.
- Không dùng một DataLoader singleton toàn ứng dụng với cache theo user mà không có cơ chế cô lập rõ ràng.

Spring `BatchLoaderRegistry` tạo DataLoader theo GraphQL execution, giúp cache mặc định được giới hạn theo request. Không nên thay đổi scope này tùy tiện khi tối ưu hiệu năng; cache dài hơn request cần thiết kế invalidation, phân vùng và bảo mật riêng.

## 10. Context và security: tránh tin dữ liệu từ client

Context thường chứa dữ liệu ảnh hưởng đến phạm vi truy cập. Cần xác định nguồn của từng giá trị:

| Giá trị context | Nguồn nên dùng | Lưu ý |
| --- | --- | --- |
| `tenantId` | Principal, token đã xác minh hoặc tenant resolver kiểm tra quyền | Không tin trực tiếp header/argument chưa xác minh. |
| `principal` | Spring Security authentication | Không lưu raw credential hoặc access token nếu không cần. |
| `locale` | Locale đã được parse/validate từ request | Chỉ dùng cho nội dung, không dùng làm căn cứ cấp quyền. |
| `correlationId` | Request header đã được chuẩn hóa hoặc sinh ở gateway | Dùng để trace, không dùng làm định danh người dùng. |
| Feature flags | Server-side feature service/configuration | Không để client tự bật quyền hoặc tính năng nội bộ. |

Batch loader nên áp dụng tenant filter ngay trong truy vấn:

```java
public Flux<Author> findByTenantAndIds(String tenantId, Set<Long> ids) {
    return repository.findAllByTenantIdAndIdIn(tenantId, ids);
}
```

Không nên tải tất cả tác giả theo ID rồi lọc tenant ở memory nếu database có thể thực hiện điều kiện đó. Truy vấn có phạm vi tenant giảm nguy cơ lộ dữ liệu và tránh tải bản ghi không được phép.

Nếu người dùng có quyền khác nhau trên từng tác giả, chỉ tenant filter có thể chưa đủ. Service phải áp dụng authorization phù hợp, hoặc batch loader phải nhận context đủ để gọi một service đã kiểm tra quyền. Không coi việc ID khó đoán là một biện pháp bảo mật.

## 11. Không dùng ThreadLocal để truyền request context

Reactive execution có thể chuyển tiếp giữa nhiều thread. Vì vậy, không nên dựa vào `ThreadLocal` tùy ý để truyền tenant hoặc principal từ interceptor đến batch loader. Một request có thể tiếp tục trên thread khác, và thread pool có thể được dùng lại cho request khác.

Hãy dùng các cơ chế context có chủ đích:

- `GraphQLContext` cho metadata gắn với GraphQL execution.
- `BatchLoaderEnvironment` cho context ở batch loader.
- Reactor Context cho metadata trong reactive pipeline khi cần tích hợp ở tầng Reactor.
- Spring Security context propagation theo cấu hình của ứng dụng.

Không lưu context request vào field của singleton service hoặc static variable. Các đối tượng đó có thể được nhiều request truy cập đồng thời, dẫn đến rò rỉ dữ liệu giữa người dùng.

## 12. Xử lý context thiếu hoặc không hợp lệ

Batch loader cần quy định rõ hành vi nếu context không tồn tại hoặc không có tenant:

```java
registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) -> {
            Object value = environment.getContext();
            if (!(value instanceof GraphQLContext context)) {
                return Mono.error(new IllegalStateException(
                        "GraphQL request context is missing"));
            }

            String tenantId = context.get("tenantId");
            if (tenantId == null || tenantId.isBlank()) {
                return Mono.error(new IllegalStateException(
                        "Authorized tenant is required"));
            }

            return authorService.findByTenantAndIds(tenantId, authorIds)
                    .collectMap(Author::id);
        });
```

Ví dụ này chọn fail-fast nếu context cần thiết bị thiếu. Tùy ứng dụng, có thể dùng exception riêng và ánh xạ thành GraphQL error phù hợp. Không nên âm thầm chuyển sang truy vấn không giới hạn tenant khi context bị thiếu; điều đó có thể biến lỗi cấu hình thành rủi ro lộ dữ liệu.

Nếu một GraphQL operation có thể chạy ở chế độ anonymous, hãy thiết kế rõ loader nào được phép hoạt động không có principal và loader nào bắt buộc phải có context xác thực. Không giả định mọi request đều có cùng mức quyền.

## 13. Kiểm thử DataLoader context

Kiểm thử cần chứng minh context được truyền đúng, batch loader dùng đúng tenant và dữ liệu của request khác không bị trộn lẫn.

Ví dụ kiểm thử qua GraphQL request với hai tenant:

```java
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@Test
void batchLoaderUsesTenantFromGraphQlContext() {
    HttpGraphQlTester tenantGraphQlTester = graphQlTester.mutate()
            .headers(headers -> headers.set("X-Tenant", "tenant-a"))
            .build();
    tenantGraphQlTester.document("""
                    query {
                        books {
                            id
                            author { id name }
                        }
                    }
                    """)
            .execute()
            .path("books[0].author.name")
            .entity(String.class)
            .isEqualTo("Author A");
}
```

Ví dụ giả định `graphQlTester` ban đầu là một `HttpGraphQlTester`, interceptor đọc `X-Tenant`, xác minh quyền của người gọi rồi đặt `tenantId` vào GraphQLContext; fixture `tenant-a` có tác giả tên `Author A`. Không nên bỏ bước xác minh chỉ để test đơn giản.

Nên bổ sung các test:

1. Batch loader nhận đúng tenant từ GraphQLContext.
2. Context thiếu hoặc tenant không hợp lệ khiến request thất bại theo chính sách.
3. Hai request đồng thời với hai tenant khác nhau không nhận nhầm dữ liệu.
4. Nhiều resolver load cùng key trong một request được gom batch và cache đúng phạm vi.
5. Key không có kết quả không làm sai thứ tự hoặc kết quả của các key còn lại.
6. Locale hoặc feature metadata được truyền đúng khi batch loader cần dùng.
7. Cancellation hoặc lỗi của batch không để lại state request trong singleton.

Có thể kiểm tra số lần gọi repository để xác nhận batching, nhưng test cũng cần xác nhận kết quả theo tenant. Chỉ đếm số query giảm chưa đủ nếu loader vô tình trả dữ liệu của tenant khác.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| `environment.getContext()` không có tenant | Interceptor chưa đưa tenant vào GraphQLContext hoặc key không thống nhất | Kiểm tra request interceptor và context key. |
| Resolver đọc được context nhưng batch loader không đọc được | Loader không đăng ký qua BatchLoaderRegistry hoặc context propagation bị tùy biến sai | Kiểm tra registry đang được GraphQlSource sử dụng và BatchLoaderEnvironment. |
| Batch loader trả dữ liệu sai tenant | Tenant lấy từ input/header chưa được xác minh hoặc cache bị chia sẻ sai | Lấy tenant từ security context đã xác thực, lọc ở repository và kiểm tra cache scope. |
| Context của request trước xuất hiện ở request sau | Dùng singleton mutable field hoặc ThreadLocal không được dọn đúng | Dùng GraphQLContext theo execution và tránh state toàn cục. |
| Cùng key trả kết quả khác nhau trong một request nhưng cache chỉ trả một giá trị | Kết quả phụ thuộc context không có trong key/cache policy | Bảo đảm context cố định theo request hoặc đưa dimension đó vào key. |
| Dùng `@ContextValue` nhưng giá trị bị thiếu | Context key không được thêm hoặc annotation yêu cầu giá trị bắt buộc | Kiểm tra interceptor; chọn required/optional theo contract. |
| Dùng `@Argument` để truyền tenant cho mọi resolver | Trộn metadata request với input nghiệp vụ và tăng nguy cơ client giả mạo | Đưa tenant đã xác minh vào GraphQLContext. |

## 15. Checklist thiết kế DataLoader context

1. Xác định metadata nào thực sự cần dùng trong batch loader.
2. Đưa metadata request vào GraphQLContext trước khi GraphQL execution bắt đầu.
3. Lấy tenant/principal từ nguồn đã xác thực và kiểm tra quyền trước khi đưa vào context.
4. Đăng ký loader bằng `BatchLoaderRegistry` để Spring quản lý DataLoader theo request.
5. Đọc context từ `BatchLoaderEnvironment` trong callback batch loader.
6. Dùng context chung cho request; chỉ dùng per-key context khi từng key thực sự có metadata khác nhau.
7. Bảo đảm key và cache scope không làm lẫn kết quả giữa tenant, locale hoặc quyền khác nhau.
8. Lọc dữ liệu ngay ở service/repository theo context và authorization.
9. Không dùng ThreadLocal hoặc singleton mutable field để giữ request metadata.
10. Kiểm thử context thiếu, context khác nhau giữa hai request và trường hợp load cùng key.

DataLoader context giúp batch loader thực thi đúng trong môi trường request hiện tại mà không phải biến tenant, principal hay locale thành các argument lặp lại. Trong Spring for GraphQL, `GraphQLContext` kết hợp với `BatchLoaderRegistry` và `BatchLoaderEnvironment` tạo ra đường truyền context rõ ràng. Khi nguồn context đã được xác thực, cache được giới hạn đúng phạm vi và batch loader luôn lọc dữ liệu theo quyền, ứng dụng vừa giảm N+1 vừa tránh trộn dữ liệu giữa các request.

Tài liệu tham khảo: [Spring for GraphQL — Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution-batching) và [GraphQL Java — DataLoader](https://github.com/graphql-java/java-dataloader).
