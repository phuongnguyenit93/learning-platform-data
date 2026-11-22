# ExecutionInput

GraphQL Java thực thi một operation thông qua đối tượng ExecutionInput. Đối tượng này gom toàn bộ dữ liệu cần thiết cho một lần chạy GraphQL: document, operation name, variables, context, root object, DataLoader registry, execution ID, locale và một số metadata khác.

ExecutionInput là ranh giới giữa request của ứng dụng và GraphQL engine. Khi gọi GraphQL.execute(input), engine dùng input để parse, validate và thực thi operation trên GraphQLSchema đã được cấu hình.

Trong Spring for GraphQL, HTTP, WebSocket hoặc RSocket request được chuyển thành GraphQlRequest/ExecutionGraphQlRequest. Spring tạo ExecutionInput từ request đó rồi gọi GraphQL Java thông qua ExecutionGraphQlService. Nếu cần bổ sung dữ liệu cho một lần thực thi, ứng dụng có thể tùy biến ExecutionInput tại interceptor của transport.

## ExecutionInput là gì?

ExecutionInput là đối tượng đầu vào cho một lần GraphQL execution. Nó không phải GraphQL document đã parse và cũng không phải GraphQL response. Nó chứa document dạng chuỗi cùng những giá trị hỗ trợ engine xử lý document đó.

Các nhóm dữ liệu chính:

| Thành phần | Vai trò |
| --- | --- |
| query | GraphQL document dạng chuỗi, có thể chứa một hoặc nhiều operation |
| operationName | Chọn operation cần chạy khi document có nhiều operation |
| variables | Giá trị đầu vào cho các biến khai báo trong operation |
| GraphQLContext | Context dùng chung cho toàn bộ data fetcher của một execution |
| root | Source object ban đầu cho các top-level field |
| localContext | Context ban đầu được cung cấp cho root data fetcher và có thể truyền tiếp xuống field con |
| DataLoaderRegistry | Registry chứa các DataLoader được dùng trong execution |
| executionId | Định danh của lần thực thi |
| locale | Locale gắn với operation |
| extensions | Metadata mở rộng theo giao thức hoặc implementation |

ExecutionInput được tạo qua Builder. Sau khi build, hãy xem input như một giá trị đầu vào ổn định; nếu cần thay đổi, tạo một input mới từ transform hoặc từ builder.

## Vòng đời của ExecutionInput

Với Spring for GraphQL, luồng xử lý phổ biến:

~~~mermaid
flowchart TD
    A["HTTP / WebSocket / RSocket request"] --> B["GraphQlRequest"]
    B --> C["WebGraphQlInterceptor / RSocketQlInterceptor"]
    C --> D["ExecutionGraphQlRequest"]
    D --> E["Tạo và tùy biến ExecutionInput"]
    E --> F["ExecutionGraphQlService"]
    F --> G["GraphQL Java"]
    G --> H["Parse và validate document"]
    H --> I["Thực thi operation"]
    I --> J["ExecutionResult"]
~~~

Transport adapter đọc request từ giao thức tương ứng. Với HTTP POST, payload thường chứa query, operationName, variables và extensions. Spring tạo request abstraction rồi chuyển request vào interceptor chain.

Sau interceptor, ExecutionGraphQlService tạo ExecutionInput và gọi GraphQL Java. GraphQL Java parse document, validate schema, chọn operation, coerce variables rồi chạy các data fetcher. Kết quả cuối cùng được bọc thành GraphQlResponse để transport ghi về client.

Điểm quan trọng là ExecutionInput đại diện cho một lần thực thi. Không dùng chung một ExecutionInput chứa state theo request cho nhiều client hoặc nhiều lần gọi.

## Tạo ExecutionInput bằng Builder

Ví dụ độc lập với Spring:

Giả sử biến graphQL đã trỏ tới một GraphQL instance được tạo từ schema và runtime wiring:

~~~java
import graphql.ExecutionInput;
import graphql.ExecutionResult;
import graphql.GraphQL;
import org.dataloader.DataLoaderRegistry;

import java.util.Locale;
import java.util.Map;

ExecutionInput input = ExecutionInput.newExecutionInput()
        .query("""
                query BookDetails($id: ID!) {
                    book(id: $id) {
                        id
                        title
                    }
                }
                """)
        .operationName("BookDetails")
        .variables(Map.of("id", "book-42"))
        .graphQLContext(context -> {
            context.put("tenantId", "tenant-01");
            context.put("requestSource", "catalog-api");
        })
        .localContext(Map.of("traceGroup", "book-details"))
        .locale(Locale.forLanguageTag("vi-VN"))
        .extensions(Map.of("clientVersion", "2.4"))
        .dataLoaderRegistry(new DataLoaderRegistry())
        .build();

ExecutionResult result = graphQL.execute(input);
~~~

Trong ví dụ:

- query là document GraphQL cần thực thi.
- operationName chọn operation BookDetails.
- variables cung cấp giá trị cho biến id.
- graphQLContext thêm dữ liệu dùng chung cho các data fetcher.
- root cung cấp source object ban đầu cho root field.
- localContext cung cấp context ban đầu cho root data fetcher.
- locale xác định locale của operation.
- extensions mang metadata mở rộng.
- dataLoaderRegistry cung cấp các DataLoader của execution.

Khi dùng Spring for GraphQL, phần lớn các giá trị query, operationName, variables, extensions và locale được framework tạo từ request transport. Ứng dụng thường chỉ cần bổ sung context, root hoặc metadata thực sự cần thiết.

## Query document và operationName

query là chuỗi GraphQL document. Một document có thể chứa một operation hoặc nhiều operation cùng fragment:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    id
    title
  }
}

query RecentBooks($limit: Int!) {
  recentBooks(limit: $limit) {
    id
    title
  }
}
~~~

Nếu document chứa nhiều operation, client phải gửi operationName để GraphQL engine biết operation nào cần thực thi. Nếu document chỉ có một operation, operationName có thể không cần thiết.

Ví dụ input chọn RecentBooks:

~~~java
ExecutionInput input = ExecutionInput.newExecutionInput()
        .query(document)
        .operationName("RecentBooks")
        .variables(Map.of("limit", 10))
        .build();
~~~

Operation name giúp log, tracing và metric phân loại loại query dễ hơn. Nên đặt tên operation có ý nghĩa như BookById hoặc RecentBooks thay vì để operation ẩn danh trong ứng dụng client.

Nếu operationName không khớp operation trong document, hoặc document có nhiều operation nhưng không chọn operation, GraphQL validation/execution sẽ trả lỗi. Resolver không được gọi trong trường hợp operation không thể được chọn hợp lệ.

## Variables và quá trình coercion

Variables tách giá trị đầu vào khỏi query string:

~~~graphql
query BookById($id: ID!, $includeReviews: Boolean!) {
  book(id: $id) {
    id
    title
    reviews @include(if: $includeReviews) {
      rating
    }
  }
}
~~~

Tạo input:

~~~java
Map<String, Object> variables = Map.of(
        "id", "book-42",
        "includeReviews", true);

ExecutionInput input = ExecutionInput.newExecutionInput()
        .query(document)
        .operationName("BookById")
        .variables(variables)
        .build();
~~~

Các key trong variables không có ký hiệu $. Key là tên biến được khai báo trong operation. Giá trị có thể là scalar, list hoặc nested map tương ứng với input object.

ExecutionInput.Builder.variables nhận raw variables. GraphQL Java sẽ kiểm tra kiểu, áp dụng default value và coercion theo khai báo của schema trong quá trình xử lý operation. Vì vậy, không nên tự ép kiểu giá trị biến ở interceptor rồi giả định việc đó thay thế được GraphQL variable coercion.

Phân biệt ba trường hợp:

| Trường hợp | Ý nghĩa |
| --- | --- |
| Biến bị bỏ khỏi map | GraphQL có thể dùng default value nếu operation khai báo |
| Biến có giá trị null | Giá trị null được truyền rõ ràng và có quy tắc riêng với biến non-null |
| Biến có kiểu không tương thích | GraphQL trả lỗi coercion/validation trước khi gọi resolver liên quan |

Không nối variables trực tiếp vào query string. Dùng variables giúp giữ document ổn định, giảm rủi ro lỗi escape và hỗ trợ operation caching.

## GraphQLContext: context dùng chung cho execution

GraphQLContext là map key-value gắn với một lần GraphQL execution. Mọi data fetcher trong execution có thể đọc cùng context này qua DataFetchingEnvironment hoặc parameter injection của Spring for GraphQL.

Context thường chứa:

- Principal hoặc thông tin người dùng đã xác thực.
- Tenant ID đã được kiểm tra.
- Correlation ID hoặc request metadata.
- Locale hoặc feature flag đã được xác thực.
- Các dịch vụ hoặc object dùng chung trong một execution nếu thực sự cần.

Tạo context khi dùng GraphQL Java trực tiếp:

~~~java
ExecutionInput input = ExecutionInput.newExecutionInput()
        .query(document)
        .graphQLContext(context -> {
            context.put("tenantId", tenantId);
            context.put("principal", principal);
        })
        .build();
~~~

Trong data fetcher GraphQL Java:

~~~java
DataFetcher<BookView> bookFetcher = environment -> {
    String tenantId =
            environment.getGraphQlContext().get("tenantId");

    String id = environment.getArgument("id");
    return bookService.findVisibleBook(tenantId, id);
};
~~~

Trong annotated controller của Spring for GraphQL, có thể nhận context trực tiếp:

~~~java
import graphql.GraphQLContext;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public BookView book(
            @Argument String id,
            GraphQLContext context) {

        String tenantId = context.get("tenantId");
        return bookService.findVisibleBook(tenantId, id);
    }
}
~~~

Hoặc dùng @ContextValue nếu chỉ cần một giá trị:

~~~java
import org.springframework.graphql.data.method.annotation.ContextValue;

@QueryMapping
public BookView book(
        @Argument String id,
        @ContextValue("tenantId") String tenantId) {
    return bookService.findVisibleBook(tenantId, id);
}
~~~

GraphQLContext được thiết kế để dùng an toàn khi nhiều data fetcher chạy đồng thời. Tuy vậy, object được lưu làm value có thể không thread-safe. Ưu tiên lưu dữ liệu request ổn định; tránh đưa mutable collection hoặc state có thể bị nhiều resolver cập nhật đồng thời vào context.

GraphQLContext yêu cầu key và value không null. Nếu không có giá trị, hãy bỏ key hoặc dùng kiểu biểu diễn optional phù hợp thay vì put null.

## Không dùng legacy context API cho code mới

GraphQL Java có API context cũ dựa trên Object:

~~~java
ExecutionInput input = ExecutionInput.newExecutionInput()
        .query(document)
        .context(legacyContext)
        .build();
~~~

Builder method context(Object) đã deprecated. Với code mới, dùng graphQLContext(...) để có context map rõ ràng và hỗ trợ nhiều thành phần phối hợp.

Tương tự, trong data fetcher hãy ưu tiên environment.getGraphQlContext() thay cho API getContext() cũ. Khi nâng cấp GraphQL Java, kiểm tra các method deprecated để tránh phụ thuộc vào API legacy.

## localContext: dữ liệu truyền từ parent field xuống child field

localContext khác GraphQLContext:

- GraphQLContext dùng chung cho toàn bộ execution.
- localContext gắn với nhánh field cụ thể, thường được parent resolver truyền xuống child resolver.
- Source object là object trả về từ parent resolver, còn localContext là dữ liệu bổ sung không nhất thiết nằm trong domain object.

Ví dụ, root resolver tải Book và tính thêm quyền hiển thị review. Quyền này chỉ cần cho các field con của Book:

~~~java
import graphql.execution.DataFetcherResult;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;

@QueryMapping
public DataFetcherResult<BookView> book(@Argument String id) {
    BookView book = bookService.findById(id);
    BookFieldPermissions permissions =
            permissionService.permissionsFor(book);

    return DataFetcherResult.<BookView>newResult()
            .data(book)
            .localContext(permissions)
            .build();
}
~~~

Nested resolver có thể đọc local context:

~~~java
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.SchemaMapping;

@SchemaMapping(typeName = "Book", field = "reviews")
public List<ReviewView> reviews(
        BookView book,
        DataFetchingEnvironment environment) {

    BookFieldPermissions permissions =
            environment.getLocalContext();

    if (!permissions.canReadReviews()) {
        return List.of();
    }

    return reviewService.findByBookId(book.id());
}
~~~

DataFetcherResult.localContext được truyền cho các field con của kết quả tương ứng. Nếu một parent field khác trả local context riêng, nhánh đó có context riêng. Điều này giúp tránh đưa metadata chỉ có ý nghĩa ở một nhánh vào context toàn operation.

ExecutionInput.localContext đặt local context ban đầu cho các root data fetcher. Sau đó parent field có thể trả DataFetcherResult.localContext để truyền dữ liệu cụ thể xuống cây field con.

## Root object

root là source object ban đầu dùng cho top-level field khi chạy GraphQL Java trực tiếp. Ví dụ một ứng dụng có thể cung cấp một facade làm root.

Schema tương ứng có field apiVersion:

~~~graphql
type Query {
  apiVersion: String!
}
~~~

~~~java
public class QueryRoot {

    private final String apiVersion;

    public QueryRoot(String apiVersion) {
        this.apiVersion = apiVersion;
    }

    public String getApiVersion() {
        return apiVersion;
    }
}
~~~

Tạo input:

~~~java
ExecutionInput input = ExecutionInput.newExecutionInput()
        .query("""
                query {
                    apiVersion
                }
                """)
        .root(new QueryRoot("catalog-api"))
        .build();
~~~

Với default property fetcher, field apiVersion có thể đọc từ getter getApiVersion() trên root object. Root object cũng có thể được đọc trực tiếp qua DataFetchingEnvironment.getRoot() trong custom data fetcher. Nếu field cần argument như book(id: ID!), hãy đăng ký custom data fetcher để đọc argument từ environment; GraphQL Java không tự truyền argument vào getter thông thường của POJO.

Trong Spring for GraphQL, annotated controller thường xử lý root mapping thông qua @QueryMapping và @MutationMapping. Ứng dụng không cần tạo QueryRoot chỉ để dùng annotated controllers. Chỉ cấu hình root khi dùng GraphQL Java trực tiếp hoặc có custom data fetcher cần source object ban đầu.

## DataLoaderRegistry

DataLoaderRegistry chứa các DataLoader mà data fetcher có thể truy cập trong một execution. Mỗi DataLoader thường gom nhiều key thành một batch, giúp giảm N+1.

Ví dụ tạo registry độc lập:

~~~java
import org.dataloader.DataLoaderFactory;
import org.dataloader.DataLoaderRegistry;
import org.dataloader.MappedBatchLoader;

import java.util.Set;
import java.util.concurrent.CompletableFuture;

MappedBatchLoader<String, AuthorView> authorBatchLoader =
        (Set<String> ids) -> CompletableFuture.completedFuture(
                authorService.findViewsByIds(ids));

DataLoaderRegistry registry = new DataLoaderRegistry();
registry.register(
        "authorLoader",
        DataLoaderFactory.newMappedDataLoader(authorBatchLoader));

ExecutionInput input = ExecutionInput.newExecutionInput()
        .query(document)
        .dataLoaderRegistry(registry)
        .build();
~~~

Không dùng lại cùng DataLoaderRegistry hoặc DataLoader giữa các execution. DataLoader thường có cache theo key trong suốt một request; nếu chia sẻ registry giữa request, dữ liệu có thể rò giữa người dùng hoặc tenant và cache có thể trả dữ liệu cũ.

Với Spring for GraphQL, nên đăng ký batch loader thông qua BatchLoaderRegistry. Spring tạo DataLoaderRegistry tương ứng cho từng request và kết nối với ExecutionInput:

~~~java
@Configuration
public class AuthorDataLoaderConfig {

    public AuthorDataLoaderConfig(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(String.class, AuthorView.class)
                .registerMappedBatchLoader((ids, environment) ->
                        authorService.findByIds(ids));
    }
}
~~~

BatchLoaderRegistry quản lý việc đăng ký loader ở tầng Spring. Không tự tạo một DataLoaderRegistry singleton rồi gắn vào mọi ExecutionInput.

## Extensions

extensions là map metadata mở rộng do transport hoặc implementation sử dụng. Nó thường xuất hiện trong các giao thức GraphQL client/server có phần mở rộng riêng.

Ví dụ, persisted query protocol có thể truyền hash hoặc thông tin phiên bản trong extensions. Một số client cũng dùng extensions để gửi metadata tương thích với server.

Không dùng extensions thay cho variables hoặc GraphQLContext:

- Dữ liệu nghiệp vụ mà query cần phải khai báo thành variables hoặc input object.
- Context của ứng dụng như principal và tenant nên đặt trong GraphQLContext.
- Extensions dành cho metadata mở rộng của giao thức hoặc implementation.

Không tin tưởng extensions do client gửi. Server cần kiểm tra format, quyền và phạm vi sử dụng trước khi dùng metadata đó.

## ExecutionId và tracing

ExecutionId định danh một lần thực thi GraphQL. GraphQL Java có thể cấp ID mặc định hoặc ứng dụng cung cấp ID riêng.

ExecutionId hữu ích cho:

- Liên kết log với một lần GraphQL execution.
- Tìm trace hoặc sự kiện tương ứng trong hệ thống observability.
- Phân biệt hai request gửi cùng document và variables.
- Điều tra lỗi hoặc độ trễ của một operation cụ thể.

Không dùng ExecutionId làm bằng chứng xác thực hoặc quyền truy cập. Nó chỉ là định danh quan sát.

Trong Spring for GraphQL, ExecutionGraphQlRequest có transport-assigned ID và có thể chuyển ID đó thành ExecutionId trong ExecutionInput. Nếu cần quy tắc riêng, GraphQL.Builder hỗ trợ ExecutionIdProvider; cấu hình engine dùng chung qua GraphQlSourceBuilderCustomizer.

Không nhầm ExecutionIdProvider với việc sửa ExecutionInput cho từng request. ExecutionIdProvider tạo ID theo chính sách của engine, còn WebGraphQlInterceptor có thể đặt ExecutionId hoặc bổ sung các giá trị request cụ thể.

## Locale

locale là Locale gắn với operation. DataFetchingEnvironment cung cấp locale để data fetcher hoặc scalar tùy biến dùng khi định dạng hoặc xử lý dữ liệu theo ngôn ngữ.

Ví dụ:

~~~java
DataFetcher<String> priceFetcher = environment -> {
    Locale locale = environment.getLocale();
    BigDecimal price = environment.getSource();
    return NumberFormat.getCurrencyInstance(locale).format(price);
};
~~~

Không nên dùng locale làm căn cứ phân quyền. Locale chỉ ảnh hưởng cách biểu diễn hoặc xử lý theo ngôn ngữ/khu vực. Spring transport có thể cung cấp locale từ request; nếu cần quy tắc riêng, có thể cấu hình qua ExecutionInput.

## Tùy biến ExecutionInput trong Spring for GraphQL

Spring for GraphQL cung cấp WebGraphQlInterceptor để kiểm tra request và tùy biến ExecutionInput trước khi GraphQL Java thực thi.

Interceptor phù hợp khi cần:

- Đưa principal đã xác thực vào GraphQLContext.
- Bổ sung tenant hoặc request metadata sau khi kiểm tra.
- Đặt execution ID hoặc locale theo chính sách request.
- Ghi nhận thông tin transport cần dùng trong data fetcher.

Ví dụ bổ sung tenant ID vào context:

~~~java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class TenantContextInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String tenantId =
                request.getHeaders().getFirst("X-Tenant-Id");

        if (tenantId != null && !tenantId.isBlank()) {
            request.configureExecutionInput((input, builder) ->
                    builder.graphQLContext(context ->
                            context.put("tenantId", tenantId))
                            .build());
        }

        return chain.next(request);
    }
}
~~~

Controller đọc giá trị:

~~~java
@QueryMapping
public BookView book(
        @Argument String id,
        @ContextValue("tenantId") String tenantId) {
    return bookService.findVisibleBook(tenantId, id);
}
~~~

Ví dụ trên minh họa kỹ thuật truyền metadata từ transport vào execution context. Trong hệ thống thực tế, không coi header X-Tenant-Id do client gửi là bằng chứng quyền truy cập. Hãy xác thực tenant với principal hoặc claim đã được kiểm tra trước khi ghi vào context; service vẫn phải áp dụng authorization khi truy vấn dữ liệu.

configureExecutionInput nhận một BiFunction gồm ExecutionInput hiện tại và ExecutionInput.Builder. Input đã được điền trước các giá trị từ request; builder giúp bổ sung hoặc thay đổi một số thành phần rồi build input mới. Nhờ vậy, các giá trị query, variables và operationName của client vẫn được giữ nguyên nếu interceptor chỉ thêm GraphQLContext.

## Phân biệt interceptor với GraphQlSourceBuilderCustomizer

Hai extension point có phạm vi khác nhau:

| Extension point | Phạm vi | Ví dụ |
| --- | --- | --- |
| WebGraphQlInterceptor | Từng request HTTP/WebSocket | Thêm principal, tenant, request metadata vào GraphQLContext |
| RSocketQlInterceptor | Từng request RSocket | Bổ sung context cho GraphQL over RSocket |
| ExecutionGraphQlRequest.configureExecutionInput | Từng request trước khi gọi GraphQL | Thay đổi ExecutionInput |
| GraphQlSourceBuilderCustomizer | Cấu hình GraphQL engine khi khởi tạo | ExecutionIdProvider, instrumentation, execution strategy |
| RuntimeWiringConfigurer | Cấu hình schema/runtime wiring | Đăng ký data fetcher, scalar, type resolver |

Không đưa dữ liệu riêng của người dùng vào GraphQlSourceBuilderCustomizer. GraphQlSource và GraphQL instance thường được dùng chung cho nhiều request; context theo request phải được gắn vào ExecutionInput hoặc GraphQLContext của lần thực thi đó.

Ví dụ cấu hình ExecutionIdProvider ở cấp GraphQL engine:

~~~java
import graphql.execution.ExecutionId;
import org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GraphQlExecutionConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer executionIdCustomizer() {
        return builder -> builder.configureGraphQl(graphQlBuilder ->
                graphQlBuilder.executionIdProvider(
                        (query, operationName, context) ->
                                ExecutionId.generate()));
    }
}
~~~

Ví dụ dùng package của Spring Boot 4.x. Với Spring Boot 3.x, package của GraphQlSourceBuilderCustomizer là org.springframework.boot.autoconfigure.graphql. Nếu không cần chính sách ID riêng, hãy dùng ID mặc định của Spring for GraphQL.

## RSocket và các transport khác

HTTP và WebSocket dùng WebGraphQlInterceptor. Với GraphQL over RSocket, Spring for GraphQL cung cấp RSocketQlInterceptor để tùy biến request trước khi GraphQL Java thực thi.

Không giả định HTTP header luôn tồn tại khi xử lý WebSocket hoặc RSocket. Mỗi transport có cách truyền metadata khác nhau:

- HTTP có headers và request attributes.
- WebSocket có connection initialization payload và thông tin từng operation.
- RSocket có metadata và payload theo interaction.

Hãy chuẩn hóa các thông tin ứng dụng cần dùng thành GraphQLContext sau khi đã xác thực nguồn dữ liệu. Controller và service khi đó có thể đọc context theo cùng một cách, không phụ thuộc transport.

## Thay đổi ExecutionInput bằng transform

ExecutionInput cung cấp transform để tạo một input mới dựa trên các giá trị hiện có:

~~~java
ExecutionInput updatedInput = input.transform(builder ->
        builder.locale(Locale.forLanguageTag("vi-VN")));
~~~

transform tạo Builder từ input hiện tại, áp dụng thay đổi và build một ExecutionInput mới. Các trường không thay đổi được giữ lại.

Đây là cách phù hợp khi code đã có ExecutionInput và muốn bổ sung một thay đổi nhỏ. Không cố sửa trực tiếp một input đã build bằng cách thay đổi các field nội bộ.

GraphQLContext bên trong ExecutionInput vẫn là context có thể thay đổi theo API của GraphQL Java. Tuy vậy, nên hạn chế mutate sau khi execution bắt đầu; hãy chuẩn bị dữ liệu cần thiết trước khi gọi engine để các resolver chạy song song nhìn thấy trạng thái ổn định.

## Bảo vệ dữ liệu trong ExecutionInput

ExecutionInput có thể mang thông tin quan trọng như principal, tenant, variables và extensions. Cần tuân thủ:

- Không ghi raw variables, access token, password hoặc dữ liệu cá nhân vào log.
- Không đưa quyền truy cập vào biến client có thể tự sửa mà không xác minh ở server.
- Không tái sử dụng GraphQLContext hoặc DataLoaderRegistry giữa các request.
- Không đưa state mutable dùng chung vào GraphQLContext nếu nhiều resolver có thể sửa đồng thời.
- Không coi extensions hoặc custom HTTP header là nguồn dữ liệu đáng tin nếu chưa xác thực.
- Giới hạn kích thước document và variables ở transport để tránh request quá lớn.
- Không đặt object có vòng đời dài hoặc giữ tài nguyên ngoài phạm vi request vào localContext.

Đặc biệt, tenant context chỉ giúp truyền tenant đã xác thực tới data fetcher. Repository hoặc service vẫn phải giới hạn truy vấn theo tenant; context không tự áp dụng row-level authorization.

## Kiểm thử ExecutionInput

Có thể kiểm thử ở ba cấp độ:

| Cấp độ | Công cụ | Nội dung cần kiểm tra |
| --- | --- | --- |
| GraphQL Java trực tiếp | GraphQL.execute(input) | query, operationName, variables, context, root và DataLoader |
| Execution service | ExecutionGraphQlServiceTester | ExecutionInput được cấu hình đúng trước khi chạy engine |
| Transport/interceptor | WebGraphQlTester | Header, principal, interceptor chain và response |

Ví dụ kiểm thử ExecutionInput trực tiếp:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import graphql.ExecutionInput;
import java.util.Map;

ExecutionInput input = ExecutionInput.newExecutionInput()
        .query("query Book($id: ID!) { book(id: $id) { id } }")
        .operationName("Book")
        .variables(Map.of("id", "book-42"))
        .graphQLContext(context -> context.put("tenantId", "tenant-01"))
        .build();

assertThat(input.getOperationName()).isEqualTo("Book");
assertThat(input.getVariables()).containsEntry("id", "book-42");
assertThat(input.getGraphQLContext().get("tenantId"))
        .isEqualTo("tenant-01");
~~~

Ví dụ này kiểm tra dữ liệu đã được đưa vào input. Để xác minh context đến được data fetcher, hãy chạy operation và kiểm tra kết quả hoặc spy service được gọi với tenant mong muốn.

Spring for GraphQL cung cấp ExecutionGraphQlServiceTester để kiểm thử server-side mà không cần HTTP client. Builder của tester có configureExecutionInput, cho phép đặt execution ID hoặc thay đổi input trong test:

~~~java
import graphql.execution.ExecutionId;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

ExecutionId executionId = ExecutionId.generate();

ExecutionGraphQlServiceTester tester =
        ExecutionGraphQlServiceTester.builder(executionGraphQlService)
                .configureExecutionInput((input, builder) ->
                        builder.executionId(executionId).build())
                .build();
~~~

Nếu cần kiểm thử interceptor, dùng WebGraphQlTester với WebGraphQlHandler để request đi qua interceptor chain trước khi tới ExecutionGraphQlService. Nếu cần kiểm thử HTTP transport thật, dùng HttpGraphQlTester.

Các trường hợp nên kiểm thử:

- Document có một operation và nhiều operation.
- operationName thiếu, đúng hoặc không tồn tại.
- Variables thiếu, null, sai kiểu và có default value.
- Context được thêm trước execution và đọc được từ resolver.
- localContext chỉ truyền tới đúng nhánh field con.
- DataLoaderRegistry được tạo mới cho từng execution.
- Hai request song song không dùng chung principal, tenant hoặc DataLoader cache.
- ExecutionId có thể truy vết trong log và observation.
- Interceptor không ghi đè query/variables do client gửi ngoài ý muốn.
- Metadata từ header hoặc extensions bị từ chối khi không hợp lệ.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không chọn được operation | Document có nhiều operation nhưng thiếu operationName | Gửi đúng operationName |
| Resolver không nhận được biến | Tên key trong variables không trùng khai báo hoặc biến không được truyền | Kiểm tra variable definition và map |
| Variables sai kiểu | Raw variable không tương thích với GraphQL input type | Để GraphQL coercion xác thực và sửa kiểu đầu vào |
| Context luôn null | Interceptor không gọi configureExecutionInput hoặc dùng sai key | Kiểm tra context key và interceptor chain |
| Dùng API context cũ | Builder.context(Object) đã deprecated | Dùng graphQLContext(...) |
| Field con không nhận metadata | Đã đặt localContext nhưng không trả DataFetcherResult.localContext từ parent | Trả DataFetcherResult và kiểm tra đúng nhánh |
| DataLoader trả dữ liệu của request khác | Tái sử dụng DataLoaderRegistry/DataLoader giữa execution | Tạo registry theo request hoặc dùng BatchLoaderRegistry |
| Root resolver nhận source null | Chưa cấu hình root object trong GraphQL Java trực tiếp | Cấu hình root hoặc dùng Spring annotated controller |
| ExecutionId không như mong muốn | Transport ID hoặc ExecutionIdProvider đang ghi đè | Kiểm tra request ID và cấu hình provider |
| Locale không đúng | Transport không cung cấp locale hoặc input không được tùy biến | Kiểm tra locale của request và ExecutionInput |
| Tenant bị giả mạo | Tin trực tiếp header/extension do client gửi | Xác thực tenant với principal/claim và giới hạn truy vấn ở service |
| Cấu hình engine bị rò request state | Đặt context theo người dùng trong GraphQlSourceBuilderCustomizer | Chuyển state sang WebGraphQlInterceptor và GraphQLContext |

## Nguyên tắc sử dụng ExecutionInput

Khi làm việc với ExecutionInput, hãy:

1. **Xem nó là input của một execution.** Không dùng chung object hoặc request state giữa các lần chạy.
2. **Giữ query và operationName rõ ràng.** Đặt operation name có ý nghĩa và chọn đúng operation trong document nhiều operation.
3. **Dùng variables thay cho nối chuỗi.** Để GraphQL Java thực hiện coercion theo schema.
4. **Dùng GraphQLContext cho dữ liệu toàn execution.** Principal, tenant đã xác thực và request metadata thuộc phạm vi này.
5. **Dùng localContext cho dữ liệu theo nhánh field.** Truyền từ parent xuống child bằng DataFetcherResult.localContext.
6. **Dùng root đúng mục đích.** Đây là source object ban đầu, không phải nơi chứa metadata request.
7. **Tạo DataLoaderRegistry theo request.** Trong Spring for GraphQL, ưu tiên BatchLoaderRegistry.
8. **Phân biệt extensions với context.** Extensions là metadata của giao thức, không phải nơi chứa dữ liệu nghiệp vụ tùy tiện.
9. **Quản lý executionId và locale có chủ đích.** Dùng ID cho quan sát và locale cho xử lý theo ngôn ngữ/khu vực.
10. **Tùy biến đúng tầng.** WebGraphQlInterceptor chỉnh input theo request; GraphQlSourceBuilderCustomizer chỉnh engine dùng chung.
11. **Dùng GraphQLContext thay API legacy.** Tránh Builder.context(Object) đã deprecated.
12. **Kiểm thử transport và service riêng.** Xác minh dữ liệu thực sự tới data fetcher, không chỉ kiểm tra builder.

ExecutionInput là hợp đồng đầu vào giữa ứng dụng và GraphQL Java. Nó mang document, operationName, raw variables, context, root object, local context, DataLoaderRegistry, execution ID, locale và extensions cho một lần chạy. Trong Spring for GraphQL, transport request được chuyển thành ExecutionInput qua ExecutionGraphQlService; WebGraphQlInterceptor hoặc RSocketQlInterceptor có thể bổ sung dữ liệu theo request trước khi engine thực thi. GraphQLContext dùng chung cho toàn operation, còn localContext truyền dữ liệu theo nhánh từ parent field tới child field. Tạo DataLoaderRegistry riêng cho từng request, giữ context ổn định và chỉ tùy biến đúng extension point sẽ giúp execution an toàn, dễ kiểm thử và dễ quan sát.

## Tài liệu tham khảo

- [GraphQL Java - ExecutionInput](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/ExecutionInput.html)
- [GraphQL Java - ExecutionInput.Builder](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/ExecutionInput.Builder.html)
- [GraphQL Java - GraphQLContext](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/GraphQLContext.html)
- [GraphQL Java - DataFetchingEnvironment](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/DataFetchingEnvironment.html)
- [Spring for GraphQL - Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL - Server Transports and Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL - Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
