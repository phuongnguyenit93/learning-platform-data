# Context không dùng làm shared mutable state

Một GraphQL operation có thể gọi nhiều resolver, truy cập nhiều service và chạy qua nhiều tầng xử lý. Những thành phần đó đôi khi cần dùng chung thông tin như correlation ID, locale, tenant đã được xác thực hoặc principal hiện tại. Spring for GraphQL cung cấp GraphQLContext và các cơ chế truyền context để chuyển thông tin này tới data fetcher.

Tuy nhiên, **context của một request không phải nơi lưu trạng thái mutable dùng chung cho toàn ứng dụng**. Một GraphQLContext thuộc về một lần thực thi GraphQL và có thể được nhiều resolver trong cùng operation cùng đọc. Các field của Query có thể được thực thi bất đồng bộ hoặc song song. Nếu nhiều resolver cùng sửa một object mutable trong context, kết quả có thể phụ thuộc thứ tự thực thi và gây lỗi cạnh tranh dữ liệu.

Bài học này tập trung vào ranh giới giữa request state, GraphQLContext và local context; cách đưa metadata vào context bằng WebGraphQlInterceptor; cách đọc context trong controller, DataLoader và batch mapping; cùng những lỗi thường gặp khi lưu dữ liệu request trong singleton bean, static field hoặc ThreadLocal.

## Request state là gì?

Request state là thông tin chỉ có ý nghĩa trong phạm vi một request hoặc một lần thực thi GraphQL. Ví dụ:

- Correlation ID để liên kết log của các resolver trong cùng operation.
- Locale được xác định từ request để chọn ngôn ngữ hoặc định dạng.
- Tenant đã được xác thực để giới hạn dữ liệu người dùng được phép truy cập.
- Principal hoặc thông tin xác thực đã được Spring Security xác lập.
- Metadata phục vụ tracing, audit hoặc feature evaluation trong một operation.

Những giá trị này khác với dữ liệu nghiệp vụ được lưu lâu dài trong database và khác với cache dùng chung giữa nhiều request. Request state cần được tạo hoặc xác định tại ranh giới tiếp nhận request, truyền tới nơi cần dùng, rồi kết thúc cùng vòng đời của operation.

Một ứng dụng Spring thường có nhiều bean singleton như controller, service, interceptor và repository. Singleton bean được nhiều request gọi đồng thời. Vì vậy, không nên lưu currentUser, tenantId, correlationId hoặc dữ liệu request vào field mutable của những bean này:

~~~java
@Component
public class RequestStateHolder {

    private String currentTenantId;

    public void setCurrentTenantId(String tenantId) {
        this.currentTenantId = tenantId;
    }

    public String getCurrentTenantId() {
        return currentTenantId;
    }
}
~~~

Đoạn code trên không an toàn nếu bean là singleton. Request A có thể ghi tenant A, sau đó request B ghi tenant B trước khi resolver của A đọc giá trị. Resolver của A có thể vô tình dùng tenant B và truy cập sai phạm vi dữ liệu.

Hãy truyền request state bằng tham số hoặc context có phạm vi request thay vì giữ nó trong field của bean.

## GraphQLContext là gì?

GraphQL Java cung cấp GraphQLContext như một vùng chứa key/value gắn với GraphQL execution. Spring for GraphQL đưa context này tới các data fetcher và annotated controller.

GraphQLContext chính có phạm vi toàn bộ một GraphQL operation. Nhiều resolver trong operation có thể đọc cùng context. Ví dụ, Query field và các field con có thể cùng đọc correlation ID hoặc tenant đã được xác thực.

Trong annotated controller, có thể nhận toàn bộ GraphQLContext:

~~~java
import graphql.GraphQLContext;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class RequestInfoController {

    @QueryMapping
    public String correlationId(GraphQLContext context) {
        return context.get("correlationId");
    }
}
~~~

Hoặc chỉ nhận một giá trị bằng @ContextValue:

~~~java
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;

@QueryMapping
public String correlationId(
        @ContextValue("correlationId") String correlationId) {
    return correlationId;
}
~~~

@ContextValue giúp chữ ký resolver chỉ thể hiện giá trị mà phương thức cần. Nếu key không bắt buộc, có thể đặt required = false hoặc dùng Optional phù hợp với kiểu dữ liệu.

GraphQLContext có API cho phép thêm và đọc giá trị. Tuy nhiên, việc có thể gọi put không có nghĩa mọi resolver nên cùng sửa context. Hãy xem context chính là nơi công bố metadata của execution; tạo các giá trị cần thiết trước khi GraphQL thực thi resolver, sau đó ưu tiên chỉ đọc.

## Ranh giới giữa GraphQLContext và shared mutable state

GraphQLContext được tạo cho một execution nên không tự động dùng chung giữa những HTTP request độc lập. Dù vậy, nó vẫn có thể được chia sẻ giữa nhiều field resolver trong cùng operation. Các resolver Query có thể được thực thi bất đồng bộ, vì vậy hai resolver có thể đọc hoặc ghi context gần như đồng thời.

Có ba phạm vi cần phân biệt:

| Phạm vi | Ví dụ | Có nên lưu mutable state dùng chung? |
| --- | --- | --- |
| Toàn ứng dụng | Static field, singleton service | Không lưu trạng thái riêng của request |
| Một GraphQL execution | GraphQLContext chính | Ưu tiên giá trị bất biến, thiết lập trước khi resolver chạy |
| Một nhánh dữ liệu con | Local context của một parent result | Chỉ truyền dữ liệu cần cho nhánh con; tránh chia sẻ object mutable không cần thiết |

Ví dụ không nên làm:

~~~java
@QueryMapping
public Book book(
        @Argument String id,
        GraphQLContext context) {

    context.put("currentBookId", id);
    return bookService.findById(id);
}
~~~

Nếu operation có nhiều field book được gọi với ID khác nhau, các resolver có thể ghi đè key currentBookId của nhau. Field con hoặc resolver khác không thể biết giá trị hiện tại thuộc lời gọi nào. Nếu cần truyền dữ liệu riêng của từng Book xuống field con, hãy dùng local context thay vì ghi đè một key trong context chính.

Một giá trị bất biến như correlation ID có thể được đặt một lần ở interceptor rồi đọc ở nhiều resolver. Nếu thực sự cần cấu trúc mutable trong context, phải có thiết kế đồng bộ và ranh giới sở hữu rõ ràng; phần lớn trường hợp có thể tránh bằng cách dùng record bất biến hoặc tạo kết quả riêng cho từng field.

## Đưa request metadata vào GraphQLContext

HTTP request có thể mang header như X-Correlation-Id. Spring for GraphQL cung cấp WebGraphQlInterceptor để đọc thông tin transport trước khi GraphQL Java thực thi operation và đưa dữ liệu cần thiết vào ExecutionInput.

Với header đơn giản, có thể dùng HttpRequestHeaderInterceptor có sẵn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.support.HttpRequestHeaderInterceptor;

@Configuration
public class GraphQlRequestContextConfiguration {

    @Bean
    HttpRequestHeaderInterceptor correlationIdInterceptor() {
        return HttpRequestHeaderInterceptor.builder()
                .mapHeader("X-Correlation-Id")
                .build();
    }
}
~~~

Controller đọc giá trị được đưa vào GraphQLContext:

~~~java
@Controller
public class DiagnosticController {

    @QueryMapping
    public String correlationId(
            @ContextValue("X-Correlation-Id") String correlationId) {
        return correlationId;
    }
}
~~~

Ví dụ trên giả định header luôn có mặt. Nếu header là tùy chọn, có thể đặt required = false trong @ContextValue hoặc dùng Optional<String>, rồi tự tạo correlation ID mặc định ở một tầng thống nhất.

Nếu cần kiểm tra, chuẩn hóa hoặc kết hợp nhiều giá trị trước khi đưa vào context, hãy viết WebGraphQlInterceptor riêng. Ví dụ dưới đây lấy correlation ID từ header, xác thực định dạng và chuyển nó vào GraphQLContext:

~~~java
import java.util.Map;
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

        String suppliedId = request.getHeaders().getFirst("X-Correlation-Id");
        String correlationId = isValid(suppliedId)
                ? suppliedId
                : UUID.randomUUID().toString();

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(Map.of(
                        "correlationId", correlationId))
                        .build());

        return chain.next(request);
    }

    private boolean isValid(String value) {
        return value != null && value.length() <= 100
                && value.matches("[A-Za-z0-9._-]+");
    }
}
~~~

Ví dụ này chỉ dùng header để tạo correlation ID phục vụ quan sát request. Với tenant hoặc quyền truy cập, không được tin tưởng một header tùy ý do client gửi. Hãy lấy tenant từ principal hoặc claim đã được xác thực, rồi áp dụng authorization ở service hoặc tầng truy cập dữ liệu.

Interceptor thường được đăng ký như một Spring bean và có thể được gọi cho nhiều request đồng thời. Vì vậy, interceptor nên stateless: chỉ dùng biến cục bộ trong phương thức intercept và không lưu correlation ID vào field của bean.

## Đọc context trong resolver và service

Một resolver có thể nhận context value rồi chuyển nó xuống service:

~~~java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @QueryMapping
    public List<Order> myOrders(
            @ContextValue("tenantId") String tenantId) {
        return orderService.findOrdersForTenant(tenantId);
    }
}
~~~

Ở đây tenantId phải được thiết lập từ nguồn đáng tin cậy ở tầng bảo mật hoặc interceptor đã xác thực. Service vẫn cần thực hiện kiểm tra quyền và phạm vi dữ liệu; việc có tenantId trong context không tự bảo đảm người dùng được phép truy cập tenant đó.

Nếu cần principal hiện tại, Spring for GraphQL hỗ trợ nhận java.security.Principal hoặc @AuthenticationPrincipal trong annotated controller:

~~~java
import java.security.Principal;

@QueryMapping
public List<Order> myOrders(Principal principal) {
    return orderService.findVisibleTo(principal.getName());
}
~~~

Với thông tin xác thực, nên ưu tiên Spring Security thay vì tự lưu access token hoặc mật khẩu vào GraphQLContext. Không đưa credential vào log, GraphQL response hoặc metadata observability.

## GraphQLContext và local context khác nhau

GraphQLContext chính phù hợp với dữ liệu dùng chung cho toàn execution, chẳng hạn correlation ID, locale hoặc metadata bảo mật. Có trường hợp một parent resolver đã tải dữ liệu mà chỉ các field con trong nhánh đó cần dùng. Nếu đưa dữ liệu đó vào context chính, mọi resolver trong operation đều có thể nhìn thấy nó và các lời gọi song song có thể ghi đè lẫn nhau.

**Local context** được thiết kế để truyền dữ liệu xuống một phần cây dữ liệu con. Spring for GraphQL cho phép controller trả về DataFetcherResult<T> với local context, sau đó field con đọc bằng @LocalContextValue.

Ví dụ parent resolver tải Book và Author cùng lúc:

~~~java
import graphql.GraphQLContext;
import graphql.execution.DataFetcherResult;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.LocalContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public DataFetcherResult<Book> bookById(@Argument String id) {
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

Local context được truyền cùng kết quả parent và chỉ có hiệu lực trong nhánh dữ liệu con tương ứng. Nếu operation truy vấn nhiều Book, mỗi parent result có thể mang local context riêng, tránh việc lưu prefetchedAuthor vào một key chung trong GraphQLContext chính.

Chỉ dùng local context khi dữ liệu thực sự thuộc một nhánh cụ thể. Nếu dữ liệu là metadata chung cho toàn operation, GraphQLContext chính phù hợp hơn. Nếu chỉ cần truy vấn một field quan hệ theo lô, DataLoader hoặc @BatchMapping thường là lựa chọn đúng hơn.

## Context trong DataLoader và batch mapping

DataLoader được tạo theo GraphQL request thông qua DataLoaderRegistry và BatchLoaderRegistry. Batch loader có thể đọc GraphQLContext của execution để sử dụng metadata như tenant hoặc locale. Trong annotated controller, batch mapping hỗ trợ nhận GraphQLContext hoặc @ContextValue.

Ví dụ:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.stereotype.Controller;

@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping
    public Map<Book, Author> author(
            List<Book> books,
            @ContextValue("tenantId") String tenantId) {
        return authorService.findAuthorsFor(books, tenantId);
    }
}
~~~

Batch loader dùng cùng context chính của GraphQL execution. Vì vậy, tenantId phải được thiết lập trước khi resolver hoặc batch loader chạy và không bị thay đổi trong lúc các field đang thực thi.

Khi dùng BatchLoaderWithContext trực tiếp, BatchLoaderEnvironment cung cấp GraphQLContext chung của execution và keyContexts chứa local context gắn với từng lần gọi load. Điều này cho phép loader phân biệt metadata chung của request với dữ liệu riêng của từng source object. Nếu một batch chứa nhiều tenant hoặc nhiều local context khác nhau, batch function phải xử lý đúng phạm vi cho từng key; không được áp một tenant duy nhất cho toàn batch khi các key có quyền truy cập khác nhau.

## Không dùng ThreadLocal làm kho request state

Một cách cũ để truyền thông tin request giữa các tầng là lưu vào ThreadLocal. Cách này dễ sai trong GraphQL vì resolver có thể chạy bất đồng bộ, đổi thread hoặc chạy trên executor khác. Với WebFlux, request thường đi qua Reactor pipeline và không gắn cố định với một thread.

Spring for GraphQL hỗ trợ context propagation từ transport tới GraphQL Java và data fetcher:

- Với Spring MVC, ThreadLocal context có thể được truyền qua cơ chế Micrometer Context Propagation khi có ThreadLocalAccessor phù hợp được đăng ký.
- Với Spring WebFlux, Reactor Context được truyền trong reactive pipeline; interceptor có thể thiết lập metadata cho GraphQLContext của operation.

Điều đó không có nghĩa nên tự tạo ThreadLocal để giữ tenant hoặc user. Nếu dùng ThreadLocal tùy chỉnh, phải quản lý accessor và vòng đời reset chính xác; nếu không, giá trị có thể rò sang tác vụ khác khi thread được tái sử dụng.

Hãy ưu tiên GraphQLContext cho metadata của execution, @ContextValue cho giá trị cần đọc trong controller, Reactor Context cho ngữ cảnh reactive của pipeline và Spring Security cho principal. Chỉ tích hợp ThreadLocalAccessor khi một thư viện đồng bộ thực sự cần ThreadLocal và đã có thiết kế propagation rõ ràng.

## WebSocket connection state không phải GraphQL operation state

Spring for GraphQL hỗ trợ HTTP và WebSocket. Một kết nối WebSocket có thể tồn tại lâu và mang nhiều GraphQL operation hoặc subscription khác nhau. WebGraphQlRequest có thể cung cấp request attributes hoặc WebSocket session attributes, nhưng những attributes ở phạm vi connection có vòng đời khác với GraphQLContext của một operation.

Không lưu dữ liệu mutable của một operation vào WebSocket session attributes rồi coi đó là state riêng của operation. Hai operation trên cùng connection có thể cùng tồn tại hoặc được thực thi ở các thời điểm khác nhau. Nếu cần thông tin xác thực của connection, hãy dùng cơ chế WebSocket authentication phù hợp; mỗi GraphQL execution vẫn cần context rõ ràng và không dùng một map mutable chung để truyền trạng thái giữa các operation.

Subscription cũng có vòng đời dài hơn query thông thường. Tránh tích lũy danh sách sự kiện, dữ liệu người dùng hoặc mutable state không giới hạn trong context của subscription. Khi cần trạng thái theo từng sự kiện, hãy gắn dữ liệu với publisher/event tương ứng và quản lý cleanup khi subscription bị hủy hoặc kết thúc.

## Những anti-pattern cần tránh

| Anti-pattern | Vì sao nguy hiểm | Cách thay thế |
| --- | --- | --- |
| Lưu currentUser trong field controller singleton | Request khác có thể ghi đè user hiện tại | Nhận Principal hoặc @AuthenticationPrincipal |
| Lưu tenantId vào static field | Mọi request và tenant cùng dùng một giá trị | Lấy tenant đã xác thực rồi truyền qua context |
| Nhiều resolver cùng put vào một key của GraphQLContext | Resolver chạy song song có thể ghi đè dữ liệu nhau | Thiết lập trước execution hoặc dùng local context |
| Dùng GraphQLContext làm cache toàn cục | Dữ liệu có phạm vi và vòng đời không phù hợp | Dùng cache chuyên dụng với TTL, key và invalidation rõ ràng |
| Giữ mutable request object trong singleton service | Dữ liệu request rò giữa các lời gọi đồng thời | Dùng biến cục bộ và tham số method |
| Dựa vào ThreadLocal trong resolver reactive | Thread có thể thay đổi giữa các bước | Dùng GraphQLContext hoặc Reactor Context |
| Đưa token hoặc mật khẩu vào context rồi log toàn bộ | Có thể lộ credential | Chỉ truyền metadata tối thiểu và lọc log |
| Dùng WebSocket session attribute cho từng operation | State có thể bị chia sẻ giữa nhiều operation | Tạo GraphQLContext riêng cho từng execution |

## Kiểm thử request isolation và context propagation

Kiểm thử context không chỉ xác nhận resolver đọc được một key. Cần xác nhận dữ liệu của hai request không bị trộn lẫn khi chạy đồng thời.

Một số kịch bản nên có:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Request A và B có correlation ID khác nhau | Mỗi resolver chỉ nhận ID của request tương ứng |
| Hai request có tenant khác nhau chạy đồng thời | Không có kết quả dữ liệu của tenant này xuất hiện ở tenant kia |
| Nhiều field Query đọc cùng GraphQLContext | Các giá trị metadata ổn định và không bị resolver ghi đè |
| Hai parent object có local context khác nhau | Field con nhận local context của đúng parent |
| Batch loader đọc @ContextValue | Loader dùng context của đúng execution |
| WebSocket có nhiều operation | Request state của operation không rò giữa các operation |
| Subscription kết thúc hoặc bị hủy | Tài nguyên và state gắn với subscription được giải phóng |

Có thể dùng HttpGraphQlTester hoặc WebTestClient để gửi hai request với header correlation ID khác nhau và kiểm tra response. Với tình huống cạnh tranh, chạy các request song song nhiều lần để tăng khả năng phát hiện lỗi chia sẻ state. Với local context, integration test nên truy vấn nhiều parent có dữ liệu khác nhau rồi xác nhận field con nhận đúng dữ liệu tương ứng.

Ngoài response, có thể kiểm tra log hoặc mock service để xác nhận tenant, principal và correlation ID được truyền đúng. Không ghi token hoặc dữ liệu nhạy cảm vào assertion log.

## Nguyên tắc thiết kế context và request state

Khi xây dựng Spring for GraphQL, hãy giữ các nguyên tắc sau:

1. **Xác định đúng phạm vi dữ liệu.** Dữ liệu toàn execution dùng GraphQLContext; dữ liệu riêng một nhánh dùng local context; dữ liệu nghiệp vụ lâu dài nằm trong service hoặc database.
2. **Thiết lập context tại ranh giới request.** Dùng WebGraphQlInterceptor hoặc interceptor tích hợp trước khi GraphQL thực thi resolver.
3. **Ưu tiên chỉ đọc sau khi thiết lập.** Đưa metadata bất biến vào context rồi để các resolver đọc, tránh ghi đè key chung.
4. **Không lưu request state trong singleton.** Controller, service và interceptor cần stateless hoặc chỉ giữ dependency bất biến.
5. **Dùng Spring Security cho danh tính và quyền.** Không coi header hoặc argument do client gửi là bằng chứng xác thực.
6. **Dùng local context cho dữ liệu theo parent.** Không đặt dữ liệu riêng từng object vào key chung của GraphQLContext.
7. **Hiểu context propagation.** Không giả định resolver chạy trên cùng thread; dùng GraphQLContext và Reactor Context phù hợp.
8. **Giữ DataLoader theo request.** Không tự tạo loader hoặc cache mutable ở scope toàn ứng dụng.
9. **Kiểm thử isolation.** Gửi nhiều request và operation đồng thời để xác nhận không có state rò rỉ.

GraphQLContext là nơi truyền metadata trong phạm vi một GraphQL execution, không phải kho shared mutable state của ứng dụng. Hãy tạo context ở ranh giới request, ưu tiên giá trị bất biến và chỉ đọc trong resolver. Khi dữ liệu chỉ thuộc một nhánh parent-child, dùng local context; khi dữ liệu thuộc danh tính và quyền truy cập, dùng Spring Security; khi cần tải dữ liệu liên quan theo lô, dùng DataLoader. Giữ đúng phạm vi và vòng đời của từng loại state giúp tránh race condition, rò rỉ dữ liệu giữa request và lỗi khó tái hiện trong ứng dụng Spring for GraphQL.

## Tài liệu tham khảo

- [Spring for GraphQL - Annotated Controllers: Context và Local Context](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - Server Transports và WebGraphQlInterceptor](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL - Request Execution và Context Propagation](https://docs.spring.io/spring-graphql/reference/request-execution.html)
