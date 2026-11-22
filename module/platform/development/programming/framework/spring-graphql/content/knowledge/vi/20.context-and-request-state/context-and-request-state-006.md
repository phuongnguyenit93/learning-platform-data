# Request metadata

Một GraphQL operation thường cần thêm thông tin ngoài document, variables và operation name. Ví dụ, server có thể cần correlation ID để nối log, locale để định dạng thông báo, tenant ID để giới hạn dữ liệu, hoặc thông tin xác thực để kiểm tra quyền. Những dữ liệu này được gọi chung là **request metadata**.

Với Spring for GraphQL, metadata có thể đến từ HTTP headers hoặc thông tin của transport, được kiểm tra ở tầng request rồi đưa vào **GraphQLContext** để các resolver sử dụng trong suốt một lần thực thi. Cách tổ chức này giúp handler nhận đúng dữ liệu cần thiết mà không phải đọc HTTP request trực tiếp hoặc yêu cầu client lặp lại metadata trong mọi argument.

Bài này giải thích các loại request metadata, cách thu thập metadata bằng **WebGraphQlInterceptor**, cách đưa dữ liệu vào GraphQLContext, cách đọc trong handler và service, cùng các nguyên tắc về trust boundary, lifecycle và kiểm thử.

## 1. Request metadata là gì?

Request metadata là thông tin đi kèm request để mô tả ngữ cảnh xử lý. Nó thường không phải dữ liệu nghiệp vụ mà client muốn truy vấn hoặc thay đổi.

Ví dụ:

| Metadata | Mục đích |
|---|---|
| Correlation ID / request ID | Nối log và theo dõi một request qua nhiều thành phần |
| Trace ID / span context | Theo dõi request trong distributed tracing |
| Locale / language preference | Chọn ngôn ngữ cho thông báo hoặc dữ liệu được bản địa hóa |
| Tenant ID | Giới hạn truy cập dữ liệu trong một tenant |
| Principal / authentication | Xác định người dùng hoặc service đã được xác thực |
| Client application ID | Nhận biết ứng dụng gọi API nếu đã được xác thực và cấp định danh |
| API version / feature metadata | Chọn hành vi tương thích khi API có cơ chế versioning hoặc feature flag |

Metadata có thể được truyền qua HTTP headers, thông tin kết nối, security context hoặc được tạo bởi gateway/interceptor phía server. Không phải mọi giá trị client gửi đều đáng tin cậy; server cần xác thực và chuẩn hóa trước khi dùng.

### Metadata khác với GraphQL arguments

Arguments là một phần của schema và operation:

~~~graphql
type Query {
  books(status: BookStatus, first: Int): [Book!]!
}
~~~

Client truyền status và first để quyết định dữ liệu nghiệp vụ cần lấy.

Metadata thường nằm ngoài GraphQL document, ví dụ:

~~~http
POST /graphql
Content-Type: application/json
X-Correlation-Id: req-8f3a
Accept-Language: vi-VN
Authorization: Bearer <token>
~~~

Correlation ID, ngôn ngữ và credential mô tả ngữ cảnh request. Chúng không cần được lặp lại thành arguments trong mọi field.

## 2. Các lớp metadata trong một GraphQL request

Có thể phân biệt metadata theo nơi tạo ra và phạm vi sử dụng:

| Lớp | Ví dụ | Phạm vi |
|---|---|---|
| Transport metadata | HTTP headers, URI, cookies, remote address | Phụ thuộc transport |
| Request metadata đã xác minh | Correlation ID hợp lệ, tenant được xác định từ principal | Một request |
| Execution context | GraphQLContext chứa tenant, locale, correlation ID | Một GraphQL execution |
| Field-local context | Dữ liệu chỉ cần cho một nhánh field | Một nhánh của cây resolve |
| Business input | Filter, ID, pagination arguments | Field hoặc operation cụ thể |

Trong ứng dụng HTTP, **WebGraphQlRequest** cung cấp thông tin request ở tầng web. **WebGraphQlInterceptor** có thể đọc headers và chuẩn bị execution input. Sau đó, GraphQLContext là nơi phù hợp để chia sẻ các giá trị đã được xác minh với DataFetcher và annotated controller.

Nếu ứng dụng hỗ trợ nhiều transport như HTTP, WebSocket hoặc RSocket, mỗi transport có thể có metadata riêng. Hãy chuyển những giá trị thực sự dùng chung sang GraphQLContext hoặc một abstraction ở application layer, thay vì buộc service phụ thuộc vào WebGraphQlRequest.

## 3. Vòng đời của request metadata

Một luồng xử lý HTTP điển hình:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[WebGraphQlInterceptor]
    B --> C[Đọc headers và request metadata]
    C --> D[Xác thực / chuẩn hóa / bổ sung metadata]
    D --> E[configureExecutionInput]
    E --> F[GraphQLContext]
    F --> G[GraphQL execution]
    G --> H[Controller / DataFetcher]
    H --> I[Service và repository]
    I --> J[GraphQL response]
~~~

Các bước chính:

1. Client gửi GraphQL document, variables và transport headers.
2. Interceptor đọc metadata ở tầng web.
3. Server xác minh giá trị cần tin cậy, tạo giá trị còn thiếu và chuẩn hóa định dạng.
4. Interceptor thêm metadata vào GraphQLContext của execution.
5. Resolver đọc context khi cần.
6. Metadata được dùng trong phạm vi operation và không tự trở thành state dùng chung giữa các request.

GraphQLContext giúp truyền dữ liệu theo execution một cách tường minh. Nó tránh việc resolver phải tự lấy dữ liệu từ servlet request hoặc dựa vào ThreadLocal vốn dễ gây nhầm lẫn trong xử lý async/reactive.

## 4. Đọc HTTP headers bằng WebGraphQlInterceptor

Spring for GraphQL cung cấp **WebGraphQlInterceptor** để can thiệp vào request/response ở tầng web transport.

Ví dụ, interceptor đọc correlation ID và ngôn ngữ:

~~~java
import java.util.Locale;
import java.util.UUID;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Mono;

@Component
public class RequestMetadataInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String correlationId =
                request.getHeaders().getFirst("X-Correlation-Id");

        if (!StringUtils.hasText(correlationId)) {
            correlationId = UUID.randomUUID().toString();
        }

        Locale locale = request.getHeaders()
                .getAcceptLanguageAsLocales()
                .stream()
                .findFirst()
                .orElse(Locale.ENGLISH);

        String requestId = correlationId;

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context -> {
                    context.put("correlationId", requestId);
                    context.put("locale", locale);
                }).build());

        return chain.next(request);
    }
}
~~~

Trong ví dụ:

- **request.getHeaders()** đọc HTTP headers.
- **X-Correlation-Id** được dùng nếu có giá trị hợp lệ theo chính sách của ứng dụng; nếu không, server tạo ID mới.
- **Accept-Language** được chuyển thành Locale.
- **configureExecutionInput** bổ sung metadata vào GraphQLContext trước khi operation chạy.
- **chain.next(request)** tiếp tục chuỗi xử lý GraphQL.

Ví dụ tập trung vào cấu trúc interceptor. Trong production, correlation ID từ bên ngoài cần được giới hạn độ dài và kiểm tra ký tự hợp lệ trước khi đưa vào log hoặc tracing. Locale cũng nên được giới hạn trong danh sách ngôn ngữ mà ứng dụng hỗ trợ.

### Interceptor được đăng ký như thế nào?

Khi interceptor là Spring bean, cấu hình Spring for GraphQL có thể phát hiện và đưa nó vào chuỗi interceptor của web transport. Có thể dùng thứ tự bean như **@Order** nếu ứng dụng có nhiều interceptor và cần quy định thứ tự xử lý.

Ví dụ:

~~~java
@Component
@Order(10)
public class RequestMetadataInterceptor implements WebGraphQlInterceptor {
    // ...
}
~~~

Thứ tự nên được xác định theo dependency giữa các interceptor. Ví dụ, bước xác thực cần chạy trước interceptor tạo tenant context nếu tenant được suy ra từ principal.

## 5. Đưa metadata vào GraphQLContext

GraphQLContext là một context map gắn với một lần thực thi GraphQL. Interceptor có thể thêm giá trị thông qua ExecutionInput builder:

~~~java
request.configureExecutionInput((input, builder) ->
        builder.graphQLContext(context -> {
            context.put("correlationId", correlationId);
            context.put("tenantId", tenantId);
            context.put("locale", locale);
        }).build());
~~~

Các key trong ví dụ là tên do ứng dụng quy ước. Nên gom chúng thành hằng số để tránh lỗi chính tả:

~~~java
public final class GraphQlContextKeys {

    public static final String CORRELATION_ID = "correlationId";
    public static final String TENANT_ID = "tenantId";
    public static final String LOCALE = "locale";

    private GraphQlContextKeys() {
    }
}
~~~

Sau đó:

~~~java
context.put(GraphQlContextKeys.CORRELATION_ID, correlationId);
context.put(GraphQlContextKeys.TENANT_ID, tenantId);
context.put(GraphQlContextKeys.LOCALE, locale);
~~~

GraphQLContext được chia sẻ trong phạm vi execution để các DataFetcher có thể truy cập. Không nên lưu dữ liệu mutable dùng chung giữa nhiều request trong static map hoặc singleton field của interceptor.

### Chọn kiểu dữ liệu cho context

Nên đưa vào context các kiểu dữ liệu rõ ràng:

- String cho correlation ID hoặc tenant ID đã chuẩn hóa.
- Locale cho ngôn ngữ.
- Principal hoặc đối tượng authentication đã được xác minh khi cần.
- Một request metadata record bất biến nếu có nhiều thuộc tính liên quan.

Ví dụ record:

~~~java
public record RequestMetadata(
        String correlationId,
        String tenantId,
        Locale locale) {
}
~~~

Interceptor có thể lưu một object RequestMetadata thay vì nhiều key riêng. Cách này giúp các giá trị liên quan được truyền cùng nhau và giảm nguy cơ key bị thiếu hoặc cập nhật không nhất quán.

## 6. Đọc metadata trong annotated controller bằng @ContextValue

Spring for GraphQL cung cấp **@ContextValue** để lấy một giá trị từ GraphQLContext:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(
            @ContextValue("tenantId") String tenantId,
            @ContextValue("locale") Locale locale) {

        return bookService.findBooks(tenantId, locale);
    }
}
~~~

Các tham số trên không phải GraphQL arguments. Chúng được lấy từ GraphQLContext đã được interceptor chuẩn bị.

Nếu context lưu một record:

~~~java
@QueryMapping
public List<Book> books(
        @ContextValue("requestMetadata") RequestMetadata metadata) {

    return bookService.findBooks(
            metadata.tenantId(),
            metadata.locale());
}
~~~

Nên dùng context value bắt buộc khi handler không thể hoạt động an toàn nếu thiếu metadata. Nếu một giá trị thực sự tùy chọn, hãy khai báo cách xử lý thiếu rõ ràng thay vì âm thầm sử dụng giá trị mặc định có thể sai tenant hoặc sai quyền.

## 7. Đọc GraphQLContext trực tiếp trong DataFetcher

Khi cần nhiều giá trị hoặc cần truy cập context trong DataFetcher tùy chỉnh, có thể nhận **DataFetchingEnvironment**:

~~~java
@QueryMapping
public List<Book> books(
        DataFetchingEnvironment environment) {

    GraphQLContext context = environment.getGraphQlContext();

    String correlationId = context.get("correlationId");
    String tenantId = context.get("tenantId");

    return bookService.findBooks(tenantId);
}
~~~

GraphQLContext cũng có thể được lấy từ API execution context tương ứng của GraphQL Java. Với annotated controller, **@ContextValue** thường làm chữ ký method dễ đọc hơn nếu chỉ cần một vài key.

Không nên truyền toàn bộ DataFetchingEnvironment vào service. Service nên nhận dữ liệu nghiệp vụ hoặc một request context thuần Java, chẳng hạn tenant ID và actor ID, thay vì phụ thuộc GraphQL Java.

## 8. Metadata tenant và ranh giới tin cậy

Tenant ID là metadata có ảnh hưởng trực tiếp tới dữ liệu người dùng được phép truy cập. Vì vậy, server phải xác định tenant từ một nguồn đáng tin cậy.

Không nên mặc định tin header:

~~~http
X-Tenant-Id: tenant-admin
~~~

Client có thể tự sửa header. Nếu server dùng giá trị này trực tiếp trong repository query, người dùng có thể truy cập dữ liệu tenant khác.

Các nguồn xác định tenant đáng tin cậy hơn có thể gồm:

- Tenant claim trong token đã được xác thực và kiểm tra chữ ký.
- Tenant được liên kết với principal trong hệ thống identity.
- Host/subdomain được gateway tin cậy định tuyến và server đã xác minh.
- Mapping server-side giữa authenticated client và tenant được cấp quyền.

Ví dụ, interceptor hoặc thành phần security có thể lấy tenant từ principal đã xác thực:

~~~java
String tenantId = tenantResolver.resolveFromAuthentication(authentication);
~~~

Sau đó mới thêm vào GraphQLContext:

~~~java
request.configureExecutionInput((input, builder) ->
        builder.graphQLContext(context ->
                context.put("tenantId", tenantId))
            .build());
~~~

Service vẫn cần áp dụng tenant filter trong truy vấn dữ liệu. Việc có tenantId trong context chỉ cung cấp thông tin; nó không tự động cô lập database hoặc bảo đảm authorization.

Nếu ứng dụng cho phép một principal truy cập nhiều tenant, cần kiểm tra tenant được chọn có nằm trong phạm vi quyền của principal trước khi đưa vào context.

## 9. Correlation ID và logging

Correlation ID giúp liên kết log từ nhiều lớp xử lý của cùng request:

~~~java
@QueryMapping
public Book book(
        @Argument String id,
        @ContextValue("correlationId") String correlationId) {

    log.info("Resolving book id={} correlationId={}", id, correlationId);
    return bookService.findById(id);
}
~~~

Trong thực tế, không nên buộc mọi resolver nhận correlationId nếu logging infrastructure đã quản lý trace context. Có thể dùng logging context hoặc tracing integration để gắn ID vào log một cách nhất quán.

Phân biệt:

- **Correlation ID**: mã ứng dụng dùng để liên kết các log hoặc event của một request.
- **Trace ID**: định danh trace trong distributed tracing.
- **Span ID**: định danh một đơn vị công việc trong trace.

Ba giá trị có thể liên kết với nhau nhưng không nhất thiết giống nhau. Nếu ứng dụng đã dùng Micrometer Tracing hoặc OpenTelemetry, hãy tận dụng trace context thay vì tự tạo một hệ thống tracing song song.

### Quy tắc khi nhận correlation ID từ client

- Giới hạn độ dài.
- Chỉ cho phép bộ ký tự an toàn.
- Không dùng giá trị này làm dữ liệu phân quyền.
- Không đưa nội dung tùy ý vào log format.
- Có thể tạo ID mới nếu giá trị không hợp lệ.
- Nếu cần trả ID về client, hãy dùng response header hoặc response metadata theo thiết kế transport.

Correlation ID là công cụ quan sát, không phải credential.

## 10. Locale và ngôn ngữ hiển thị

Client có thể gửi:

~~~http
Accept-Language: vi-VN,vi;q=0.9,en;q=0.8
~~~

Interceptor đọc locale rồi đưa vào GraphQLContext. Resolver hoặc service có thể dùng locale để:

- Chọn bản dịch của nội dung.
- Định dạng thông báo lỗi nghiệp vụ.
- Định dạng ngày/giờ hoặc số tiền ở tầng trình bày.
- Chọn bản ghi localized nếu domain lưu nhiều ngôn ngữ.

Không nên dùng locale để thay đổi giá trị nghiệp vụ cốt lõi. Ví dụ, giá tiền nên được trả dưới dạng số và currency code; client có thể định dạng theo locale hoặc server cung cấp field presentation riêng.

Locale nhận từ Accept-Language cần được đối chiếu với các locale được hỗ trợ. Nếu không hỗ trợ, server nên chọn fallback rõ ràng.

Ví dụ resolver:

~~~java
@QueryMapping
public Product product(
        @Argument String id,
        @ContextValue("locale") Locale locale) {

    return productService.findLocalized(id, locale);
}
~~~

## 11. Authentication và Principal

Authentication thường được xử lý bởi Spring Security trước hoặc trong chuỗi xử lý request. Request metadata interceptor có thể sử dụng thông tin xác thực đã được xác minh để đưa actor hoặc tenant vào GraphQLContext.

Nếu handler chỉ cần principal, Spring for GraphQL có thể hỗ trợ nhận **Principal** như method argument khi integration security cung cấp giá trị đó:

~~~java
@QueryMapping
public List<Book> myBooks(Principal principal) {
    return bookService.findOwnedBy(principal.getName());
}
~~~

Không nên tự đọc token thô từ Authorization header trong từng resolver. Authentication filter/security infrastructure chịu trách nhiệm xác thực credential; resolver và service sử dụng principal đã được xác minh.

Cũng không nên đưa raw bearer token vào GraphQLContext nếu không có nhu cầu cụ thể. Token là bí mật; việc sao chép nó vào context, log hoặc downstream request làm tăng nguy cơ lộ credential.

## 12. Metadata trong async và reactive execution

GraphQL handler có thể trả về CompletionStage, Mono hoặc Publisher. Quá trình thực thi có thể chuyển thread hoặc tiếp tục bất đồng bộ.

GraphQLContext gắn với execution, vì vậy DataFetcher có thể lấy metadata từ context trong phạm vi execution mà không phải dựa vào ThreadLocal.

Ví dụ:

~~~java
@QueryMapping
public Mono<List<Book>> books(
        @ContextValue("tenantId") String tenantId) {

    return bookService.findBooksReactive(tenantId);
}
~~~

Không nên giả định ThreadLocal hoặc MDC luôn tự động tồn tại khi reactive pipeline chuyển thread. Nếu dùng logging context, hãy cấu hình propagation tương ứng với tracing/logging stack. GraphQLContext phù hợp để truyền metadata cần thiết cho resolver; tracing context nên được quản lý bởi tracing integration.

Nếu gọi service ngoài, hãy truyền những giá trị cần thiết qua request object hoặc header được kiểm soát. Không truyền nguyên GraphQLContext xuống mọi service vì nó có thể chứa dữ liệu chỉ dành cho GraphQL execution.

## 13. Metadata theo transport và khả năng mở rộng nhiều transport

**WebGraphQlInterceptor** áp dụng cho web transport. Nếu ứng dụng còn hỗ trợ RSocket hoặc WebSocket, cần xem xét interceptor và metadata tương ứng của transport đó.

Không phải metadata nào cũng có thể được chuyển nguyên trạng giữa các transport:

| Metadata | HTTP | WebSocket/RSocket |
|---|---|---|
| HTTP headers | Có | Có thể chỉ có ở bước handshake hoặc setup |
| Connection metadata | Không phải khái niệm chung | Có thể có theo transport |
| Principal | Có qua security integration | Có nếu transport/security cung cấp |
| Correlation ID | Có thể nhận từ header | Có thể nhận từ handshake hoặc tạo ở server |
| Locale | Có thể nhận từ Accept-Language | Cần quy ước tương đương |
| GraphQLContext | Có trong execution | Có trong execution |

Nếu logic nghiệp vụ cần tenant hoặc actor, hãy chuyển chúng thành kiểu dữ liệu chung ở application layer. Đừng để service phụ thuộc vào HTTP headers hoặc WebSocket session.

## 14. Phân biệt GraphQLContext với local context

GraphQLContext chứa metadata dùng chung trong toàn bộ một execution. Local context được truyền từ một field cha tới các field con trong nhánh tương ứng.

| Tiêu chí | GraphQLContext | Local context |
|---|---|---|
| Phạm vi | Toàn execution | Nhánh field |
| Nguồn | ExecutionInput/context setup | DataFetcherResult của field cha |
| Ví dụ | Correlation ID, tenant, locale, actor | Display option hoặc dữ liệu phụ trợ riêng của nhánh |
| Cách đọc trong controller | @ContextValue | @LocalContextValue |

Không nên đặt metadata request như correlation ID vào local context vì các nhánh khác cũng cần dùng nó. Ngược lại, dữ liệu chỉ có ý nghĩa trong một nhánh không nên đưa vào GraphQLContext dùng chung nếu không cần.

## 15. Kiểm thử request metadata

Muốn kiểm tra interceptor đọc HTTP headers và đưa dữ liệu vào GraphQLContext, cần kiểm thử qua web transport. Một test chỉ gọi trực tiếp GraphQlService hoặc GraphQlTester ở mức execution có thể bỏ qua WebGraphQlInterceptor.

Với HTTP, có thể dùng **HttpGraphQlTester** kết hợp WebTestClient và đặt header trước khi gửi operation:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RequestMetadataTest {

    @LocalServerPort
    int port;

    @Test
    void shouldMakeCorrelationIdAvailableToResolver() {
        WebTestClient webTestClient = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .defaultHeader("X-Correlation-Id", "test-request-123")
                .defaultHeader("Accept-Language", "vi-VN")
                .build();

        HttpGraphQlTester tester = HttpGraphQlTester.create(webTestClient);

        tester.document("""
                query {
                    requestMetadata {
                        correlationId
                        language
                    }
                }
                """)
            .execute()
            .path("requestMetadata.correlationId")
            .entity(String.class)
            .isEqualTo("test-request-123");
    }
}
~~~

Ví dụ này giả định ứng dụng có field test-only requestMetadata để quan sát metadata. Không nên công khai field debug như vậy trong schema production nếu không có nhu cầu API thực tế.

Nên kiểm tra:

1. Header correlation ID hợp lệ được đưa vào context.
2. Header thiếu hoặc không hợp lệ được xử lý theo fallback.
3. Accept-Language được chuẩn hóa và chọn fallback đúng.
4. Tenant được lấy từ nguồn đã xác thực, không tin tenant header tùy ý.
5. Principal đúng với người dùng đã đăng nhập.
6. Hai request đồng thời không chia sẻ GraphQLContext.
7. Async resolver vẫn đọc được metadata.
8. Metadata không xuất hiện trong log nếu chứa thông tin nhạy cảm.
9. Interceptor được thực thi đúng thứ tự.
10. Các transport khác nhau tạo cùng abstraction metadata nếu ứng dụng hỗ trợ nhiều transport.

Nếu cần test GraphQLContext mà không kiểm tra HTTP headers, có thể dùng GraphQlTester ở execution layer và cấu hình execution input/context phù hợp. Cần phân biệt rõ test interceptor với test resolver.

## 16. Những lỗi thường gặp khi xử lý request metadata

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| @ContextValue không tìm thấy key | Interceptor chưa thêm key hoặc tên key không khớp | Dùng hằng số context key và kiểm tra interceptor |
| Header có giá trị nhưng resolver nhận null | Metadata chưa được chuyển vào GraphQLContext | Kiểm tra configureExecutionInput |
| Tenant có thể bị thay đổi bởi client | Tin trực tiếp X-Tenant-Id | Suy tenant từ authentication hoặc nguồn tin cậy |
| Correlation ID bị thiếu trong log | Chưa tạo fallback hoặc logging context chưa được propagate | Tạo ID server-side và cấu hình tracing/logging |
| Locale không đúng | Không parse Accept-Language hoặc thiếu fallback | Chuẩn hóa locale và giới hạn locale hỗ trợ |
| Context rò giữa request | Dùng static map hoặc singleton mutable state | Dùng GraphQLContext riêng từng execution |
| Metadata mất trong reactive callback | Phụ thuộc ThreadLocal/MDC | Truyền context tường minh và cấu hình propagation |
| Service phụ thuộc HTTP API | Truyền WebGraphQlRequest sâu vào application layer | Chuyển metadata thành request context/command thuần Java |
| Raw token bị ghi log | Đưa credential vào context hoặc log toàn bộ headers | Không log secret và chỉ truyền giá trị cần thiết |
| Test không chạy interceptor | Dùng tester ở execution layer thay vì web transport | Dùng HttpGraphQlTester hoặc transport tester phù hợp |

## 17. Quy trình triển khai request metadata

Khi ứng dụng cần thêm request metadata:

1. Xác định metadata phục vụ quan sát, localization, tenant hoặc authentication.
2. Chọn nguồn tạo metadata: header, security principal, gateway hoặc server.
3. Phân loại nguồn nào đáng tin cậy và nguồn nào cần xác thực/chuẩn hóa.
4. Dùng **WebGraphQlInterceptor** để đọc metadata ở web transport.
5. Tạo fallback cho giá trị tùy chọn như correlation ID hoặc locale.
6. Đưa metadata đã xác minh vào GraphQLContext qua configureExecutionInput.
7. Dùng **@ContextValue** hoặc DataFetchingEnvironment để đọc trong resolver.
8. Chuyển các giá trị cần thiết thành kiểu request context/command thuần Java trước khi gọi service.
9. Giữ tenant và actor authorization ở service/data access layer.
10. Không lưu request state trong singleton hoặc static mutable state.
11. Kiểm thử qua đúng transport và xác nhận không chia sẻ context giữa request.
12. Theo dõi correlation/tracing mà không ghi credential hoặc dữ liệu nhạy cảm.

Request metadata bổ sung ngữ cảnh cho GraphQL execution mà không làm phình schema bằng những argument lặp lại ở nhiều field. Trong Spring for GraphQL, WebGraphQlInterceptor là điểm phù hợp để đọc HTTP metadata, xác minh và đưa các giá trị cần thiết vào GraphQLContext. Resolver có thể lấy chúng qua @ContextValue hoặc DataFetchingEnvironment, còn service nên nhận dữ liệu thuần Java. Hãy đặc biệt bảo vệ tenant và identity, giữ context trong phạm vi từng execution và kiểm thử qua transport thực tế để bảo đảm metadata được truyền đúng.
