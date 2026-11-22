# GraphQLContext trong controller

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của GraphQLContext trong một lần thực thi GraphQL.
- Đưa request metadata vào GraphQLContext bằng WebGraphQlInterceptor.
- Đọc giá trị context trong annotated controller bằng @ContextValue.
- Phân biệt GraphQLContext với argument, source object và local context.
- Chọn dữ liệu phù hợp để chia sẻ giữa các resolver trong cùng request.
- Tránh lỗi bảo mật và lỗi đồng thời khi sử dụng request state.
- Kiểm thử context propagation bằng GraphQlTester.

## GraphQLContext là gì?

Khi GraphQL thực thi một operation, nhiều resolver có thể cần dùng chung thông tin của request. Ví dụ:

- Correlation ID để liên kết log của các resolver trong cùng request.
- Tenant ID đã được xác thực để giới hạn dữ liệu theo tenant.
- Locale hoặc thông tin vùng để định dạng dữ liệu.
- Feature flags hoặc metadata do server xác định.
- Thông tin tracing và cấu hình thực thi theo request.

GraphQLContext là nơi lưu các giá trị theo phạm vi một lần thực thi GraphQL. Các data fetcher và controller method có thể đọc cùng context trong quá trình xử lý operation.

Trong Spring for GraphQL, có thể thêm giá trị vào GraphQLContext trước khi thực thi bằng WebGraphQlInterceptor, sau đó đọc trong annotated controller bằng @ContextValue.

GraphQLContext không phải một biến toàn cục. Mỗi request/execution có context riêng, vì vậy dữ liệu của request này không nên rò rỉ sang request khác.

## Khi nào nên dùng GraphQLContext?

Hãy dùng context khi một giá trị là metadata hoặc state chung cho nhiều resolver trong cùng execution, thay vì là dữ liệu nghiệp vụ client truyền riêng cho một field.

| Loại dữ liệu | Cách truyền phù hợp |
| --- | --- |
| ID sách client muốn tìm | GraphQL argument qua @Argument |
| Filter hoặc input object client gửi | Input object qua @Argument |
| Object cha đang được phân giải | Source parameter trong @SchemaMapping |
| Correlation ID của request | GraphQLContext |
| Tenant ID đã xác thực và được server xác định | GraphQLContext hoặc security principal |
| Principal và quyền hiện tại | Spring Security integration, chẳng hạn @AuthenticationPrincipal |
| Dữ liệu chỉ cần truyền xuống một nhánh field con | Local context |

Không đưa mọi tham số vào GraphQLContext. Nếu một giá trị thuộc contract của field và client cần chủ động cung cấp, hãy khai báo argument hoặc input object trong SDL. Context dành cho thông tin ở phạm vi thực thi, không thay thế schema.

## Thêm giá trị vào GraphQLContext bằng WebGraphQlInterceptor

WebGraphQlInterceptor nằm ở lớp web của Spring for GraphQL. Interceptor có thể đọc thông tin request, bổ sung execution input rồi chuyển request tiếp tục qua chuỗi xử lý.

Ví dụ, ứng dụng muốn ghi correlation ID cho mỗi request. Client có thể gửi header X-Correlation-Id; nếu header không có, server tạo một ID mới:

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

        String requestCorrelationId = correlationId;

        request.configureExecutionInput((executionInput, builder) ->
                builder.graphQLContext(context ->
                        context.put("correlationId", requestCorrelationId)
                ).build()
        );

        return chain.next(request);
    }
}
~~~

configureExecutionInput cho phép tùy chỉnh ExecutionInput trước khi GraphQL engine thực thi operation. Callback graphQLContext thêm cặp key/value vào GraphQLContext. Sau đó chain.next(request) chuyển request tới interceptor tiếp theo hoặc bước thực thi.

Trong ví dụ, key là correlationId. Nên thống nhất tên key giữa interceptor và controller; nếu dùng chuỗi tùy ý ở nhiều nơi, hãy tập trung chúng thành constant để tránh lỗi đánh máy.

Interceptor là Spring bean nên được phát hiện trong application context. Với cấu hình Spring Boot for GraphQL thông thường, các WebGraphQlInterceptor bean được đưa vào chuỗi xử lý web GraphQL.

Correlation ID từ HTTP header là dữ liệu do client cung cấp. Nếu dùng giá trị đó trong log, hãy giới hạn độ dài và lọc ký tự không mong muốn. Không dùng một header tùy ý làm căn cứ phân quyền hoặc xác định tenant.

## Đọc context trong annotated controller bằng @ContextValue

Sau khi interceptor thêm giá trị, controller có thể đọc bằng @ContextValue:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

import java.util.List;

@Controller
public class BookQueryController {

    private final BookService bookService;
    private final Logger logger =
            LoggerFactory.getLogger(BookQueryController.class);

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(
            @ContextValue("correlationId") String correlationId) {

        logger.debug("Loading books for request {}", correlationId);
        return bookService.findAll();
    }
}
~~~

Spring lấy giá trị có key correlationId từ GraphQLContext và bind vào tham số method. Controller không cần nhận toàn bộ HTTP request hoặc tự đọc header.

Có thể kết hợp context với argument:

~~~java
@QueryMapping
public List<Book> books(
        @Argument("first") int first,
        @ContextValue("correlationId") String correlationId) {

    logger.debug("Request {} asks for {} books", correlationId, first);
    return bookService.findFirst(first);
}
~~~

first là dữ liệu query client gửi theo schema; correlationId là metadata của request. Hai loại dữ liệu có nguồn và mục đích khác nhau.

Nếu context key không được thiết lập, việc bind một tham số bắt buộc có thể thất bại. Hãy bảo đảm interceptor luôn đặt giá trị, hoặc thiết kế tham số tùy chọn theo API của phiên bản Spring for GraphQL đang dùng. Đừng mặc định rằng một key có thể thiếu sẽ luôn được thay bằng giá trị Java mặc định.

## Truy cập GraphQLContext trực tiếp khi cần

Trong một số trường hợp, resolver cần đọc nhiều key hoặc thao tác với context có kiểu động. Spring for GraphQL cũng hỗ trợ truy cập execution context qua DataFetchingEnvironment:

~~~java
import graphql.schema.DataFetchingEnvironment;

@QueryMapping
public List<Book> books(DataFetchingEnvironment environment) {
    String correlationId =
            environment.getGraphQlContext().get("correlationId");

    return bookService.findAll();
}
~~~

DataFetchingEnvironment chứa thông tin của field đang được thực thi, bao gồm arguments, source, GraphQLContext và selection. Chỉ dùng cách này khi method thực sự cần các thông tin đó; với một giá trị đơn giản, @ContextValue thường rõ ràng và dễ đọc hơn.

GraphQLContext có thể chứa giá trị với kiểu cụ thể. Nếu lấy giá trị qua key dạng chuỗi, hãy giữ nhất quán kiểu khi ghi và đọc:

~~~java
context.put("tenantId", tenantId);
~~~

~~~java
String tenantId = environment.getGraphQlContext().get("tenantId");
~~~

Không lưu một kiểu dữ liệu rồi đọc thành kiểu khác. Với context key dùng chung trong nhiều module, có thể định nghĩa constant và wrapper nhỏ để giảm rủi ro sai kiểu.

## Đưa tenant hoặc identity vào context một cách an toàn

Tenant ID thường được dùng để giới hạn dữ liệu. Đây là thông tin nhạy cảm về phạm vi truy cập, vì vậy phải được xác định từ danh tính đã xác thực hoặc một nguồn server-side đáng tin cậy.

Một luồng xử lý an toàn có thể gồm:

1. Spring Security xác thực request.
2. Lớp bảo mật hoặc interceptor xác định tenant mà principal hiện tại được phép truy cập.
3. Server đưa tenant ID đã được xác minh vào GraphQLContext.
4. Resolver đọc tenant ID bằng @ContextValue và truyền xuống service.
5. Service luôn áp dụng tenant constraint trong truy vấn dữ liệu.

Ví dụ controller:

~~~java
@QueryMapping
public List<Book> books(
        @Argument("first") int first,
        @ContextValue("tenantId") String tenantId) {

    return bookService.findVisibleToTenant(tenantId, first);
}
~~~

Ví dụ này giả định một thành phần server-side trước đó đã xác thực người dùng và đặt tenantId đáng tin cậy vào context. Không lấy tenant ID từ một header hoặc argument client có thể tự sửa rồi dùng trực tiếp làm ranh giới bảo mật.

Nếu ứng dụng dùng Spring Security, có thể đọc principal bằng @AuthenticationPrincipal hoặc cơ chế security context tương ứng. Không cần sao chép toàn bộ SecurityContext vào GraphQLContext chỉ để tiện truy cập. Chỉ đưa tenant ID hoặc metadata cần thiết vào GraphQLContext sau khi đã xác minh quyền.

GraphQLContext không tự thực hiện authorization. Nó chỉ vận chuyển dữ liệu trong request. Service hoặc security layer vẫn phải kiểm tra quyền đối với từng tài nguyên và hành động.

## Phân biệt GraphQLContext và local context

GraphQL Java có hai loại context cần phân biệt:

- GraphQLContext: context cấp execution, dùng chung trong phạm vi một lần thực thi GraphQL.
- Local context: dữ liệu được truyền từ resolver cha xuống các resolver con trong một nhánh của response.

Ví dụ, một resolver cha có thể trả DataFetcherResult và gắn local context:

~~~java
@QueryMapping
public DataFetcherResult<Book> book(@Argument("id") String id) {
    Book book = bookService.findById(id).orElse(null);

    return DataFetcherResult.<Book>newResult()
            .data(book)
            .localContext(Map.of("includeInternalFields", false))
            .build();
}
~~~

Resolver field con có thể đọc local context bằng @LocalContextValue:

~~~java
@SchemaMapping(typeName = "Book", field = "internalNotes")
public String internalNotes(
        Book book,
        @LocalContextValue("includeInternalFields") Boolean includeInternalFields) {

    if (!Boolean.TRUE.equals(includeInternalFields)) {
        return null;
    }
    return book.internalNotes();
}
~~~

Đây là ví dụ minh họa cơ chế truyền state theo nhánh. Trong ứng dụng thực tế, không dùng một cờ local context do resolver cha đặt làm cơ chế authorization duy nhất; field nhạy cảm vẫn phải kiểm tra quyền ở server.

Local context phù hợp khi dữ liệu chỉ có ý nghĩa cho các field con của một source object cụ thể. GraphQLContext phù hợp khi metadata được nhiều resolver ở các nhánh khác nhau sử dụng.

| Tiêu chí | GraphQLContext | Local context |
| --- | --- | --- |
| Phạm vi | Toàn execution | Nhánh resolver cha và các field con |
| Nơi thiết lập | ExecutionInput, interceptor hoặc cấu hình thực thi | Resolver cha, thường qua DataFetcherResult |
| Cách đọc trong controller | @ContextValue hoặc DataFetchingEnvironment | @LocalContextValue |
| Ví dụ | Correlation ID, tenant đã xác thực, locale | Quy tắc hoặc dữ liệu nội bộ riêng cho một nhánh |

## GraphQLContext không phải argument hay source object

Ba nguồn dữ liệu này có mục đích khác nhau:

~~~java
@SchemaMapping(typeName = "Book", field = "recommendations")
public List<Book> recommendations(
        Book source,
        @Argument("first") int first,
        @ContextValue("tenantId") String tenantId) {

    return bookService.findRecommendations(
            source.id(), tenantId, first);
}
~~~

- source là Book cha mà GraphQL đang phân giải.
- first là argument của field recommendations do client gửi.
- tenantId là context đã được server xác định cho execution.

Không đưa ID của Book vào GraphQLContext khi nó đã có sẵn trong source object. Cũng không đưa page size vào context nếu đó là argument của field và client cần điều khiển nó.

## Phạm vi sống và an toàn luồng

GraphQL có thể thực thi các field độc lập song song. Nhiều resolver có thể đọc cùng GraphQLContext trong khoảng thời gian gần nhau. Vì vậy:

- Ưu tiên lưu giá trị bất biến như String, UUID, Locale hoặc một object identity bất biến.
- Không dùng context làm nơi chứa một mutable list hoặc mutable map được nhiều resolver cùng ghi.
- Nếu cần state có thay đổi, phải xác định rõ đồng bộ và vòng đời; thường nên dùng service hoặc cơ chế chuyên biệt thay vì context chung.
- Không giữ tham chiếu GraphQLContext trong singleton bean hoặc lưu nó sang request khác.
- Không lưu dữ liệu người dùng trong static field hoặc biến instance dùng chung giữa các request.

Context thuộc một execution. Không dùng nó thay cho cache dài hạn. Nếu cần cache dữ liệu dùng chung, hãy chọn cache có phạm vi, key, invalidation và chính sách tenant rõ ràng.

## Context và DataLoader

DataLoader thường được tạo theo request/execution để gom và cache các lần tải dữ liệu. GraphQLContext và DataLoader có thể cùng tham gia một execution, nhưng chúng có trách nhiệm khác nhau:

- GraphQLContext giữ metadata và state cần chia sẻ.
- DataLoader gom các yêu cầu tải dữ liệu, dispatch batch và cache kết quả theo key.

Không tự đặt cache của DataLoader thành singleton dùng chung giữa người dùng. Với dữ liệu phụ thuộc tenant hoặc principal, loader cần được đăng ký theo execution và truy vấn phải áp dụng đúng security scope. Context có thể cung cấp tenant ID cho batch loader, nhưng batch loader vẫn phải thực hiện kiểm tra phạm vi dữ liệu.

## Kiểm thử GraphQLContext

Khi context được thêm qua WebGraphQlInterceptor, nên kiểm thử qua web GraphQL handler hoặc HTTP endpoint để xác minh cả interceptor và controller binding.

Ví dụ integration test dùng HttpGraphQlTester trong Spring Boot:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class GraphQlContextIntegrationTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Test
    void exposesCorrelationIdToResolver() {
        HttpGraphQlTester tester = graphQlTester.mutate()
                .headers(headers ->
                        headers.set("X-Correlation-Id", "test-request-123"))
                .build();

        tester.document("""
                query {
                    currentCorrelationId
                }
                """)
                .execute()
                .path("currentCorrelationId")
                .entity(String.class)
                .isEqualTo("test-request-123");
    }
}
~~~

Để test này chạy, schema và resolver cần có field trả về correlation ID:

~~~graphql
type Query {
  currentCorrelationId: String!
}
~~~

~~~java
@QueryMapping
public String currentCorrelationId(
        @ContextValue("correlationId") String correlationId) {
    return correlationId;
}
~~~

Nếu chỉ kiểm thử controller bằng một GraphQlTester không đi qua web interceptor, context cần được thêm trực tiếp vào ExecutionInput của tester hoặc test phải dùng một execution setup phù hợp. Một test controller đơn lẻ không chứng minh rằng HTTP header đã được interceptor chuyển vào context.

Nên kiểm thử:

1. Header correlation ID được chuyển vào GraphQLContext.
2. Khi thiếu header, interceptor tạo ID mặc định.
3. Resolver đọc đúng context value bằng @ContextValue.
4. Hai request có context khác nhau không chia sẻ giá trị.
5. Tenant ID được lấy từ nguồn server-side đã xác thực, không lấy trực tiếp từ input không đáng tin.
6. Local context chỉ được đọc trong nhánh resolver đã nhận nó.
7. Batch loader dùng đúng tenant scope trong cùng execution.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| @ContextValue không nhận được giá trị | Interceptor không đặt key hoặc tên key không khớp | Kiểm tra graphQLContext.put và annotation |
| Giá trị context bị null | Context key không có trong execution hiện tại | Bảo đảm mọi request path đều thiết lập giá trị hoặc xử lý optional |
| Controller không thấy giá trị từ HTTP header | Chưa có WebGraphQlInterceptor hoặc test không đi qua web layer | Kiểm tra interceptor chain và loại tester |
| Tenant có thể bị giả mạo | Lấy tenant từ header/argument client mà không xác minh | Xác định tenant từ principal hoặc nguồn server-side đáng tin |
| Request này đọc dữ liệu của request khác | Lưu context trong singleton/static state | Chỉ dùng execution context và không chia sẻ mutable state |
| Context bị ghi đè ngoài dự kiến | Nhiều interceptor dùng cùng key | Đặt quy ước key và thứ tự interceptor rõ ràng |
| Dùng GraphQLContext cho dữ liệu của một nhánh | Chọn sai phạm vi state | Dùng local context và @LocalContextValue |
| Resolver có quá nhiều tham số context | Đưa cả dữ liệu nghiệp vụ vào context | Dùng argument, source object hoặc service phù hợp |

## Thực hành tổng hợp

Xây dựng API thư viện có request metadata và tenant scope:

1. Tạo CorrelationIdInterceptor đọc X-Correlation-Id, tạo UUID nếu thiếu và đặt key correlationId vào GraphQLContext.
2. Tạo query currentCorrelationId và đọc giá trị bằng @ContextValue.
3. Tạo một thành phần xác thực xác định tenant ID từ principal hoặc nguồn server-side đáng tin.
4. Đặt tenant ID đã xác minh vào GraphQLContext.
5. Tạo query books(first: Int!) nhận first qua @Argument và tenantId qua @ContextValue.
6. Truyền tenant ID xuống service để truy vấn đúng phạm vi dữ liệu.
7. Tạo hai request với correlation ID khác nhau và xác minh context không bị chia sẻ.
8. Viết integration test đi qua HTTP interceptor; viết test riêng cho resolver khi cần.

Sau bài thực hành, hãy giải thích vì sao correlation ID có thể đến từ request header nhưng tenant ID phải được xác minh, vì sao page size thuộc argument và khi nào local context phù hợp hơn GraphQLContext.

## Ghi nhớ

GraphQLContext lưu metadata và state chung trong phạm vi một lần thực thi GraphQL. Spring for GraphQL cho phép bổ sung context qua WebGraphQlInterceptor và đọc trong annotated controller bằng @ContextValue. Hãy dùng context cho correlation ID, locale hoặc tenant đã được server xác minh; dùng @Argument cho dữ liệu client gửi và source parameter cho object cha. Local context phù hợp với dữ liệu chỉ truyền xuống một nhánh. Vì resolver có thể chạy song song, ưu tiên giá trị bất biến, không lưu context vào singleton và không dùng context thay cho authorization hoặc cache toàn cục. Kiểm thử cả interceptor chain lẫn controller binding để xác nhận dữ liệu được truyền đúng phạm vi.
