# WebGraphQlRequest

Trong Spring for GraphQL, **WebGraphQlRequest** là abstraction đại diện cho một GraphQL request đi qua web transport. Nó cung cấp nội dung GraphQL như document, operation name, variables và extensions, đồng thời cho phép truy cập thông tin của HTTP request như headers, URI, remote address và request attributes.

Đối tượng này thường được sử dụng trong **WebGraphQlInterceptor**. Interceptor có thể đọc metadata từ request, kiểm tra hoặc chuẩn hóa dữ liệu, sau đó bổ sung thông tin vào GraphQL execution input trước khi resolver chạy. Nhờ vậy, code xử lý transport được giữ ở tầng web; controller và service chỉ nhận những dữ liệu cần thiết cho use case.

Bài này trình bày cấu trúc và vòng đời của WebGraphQlRequest, các nhóm thông tin có thể truy cập, cách sử dụng request trong interceptor, cách cấu hình ExecutionInput và GraphQLContext, ranh giới giữa web request với GraphQL execution, cùng các lưu ý về bảo mật và kiểm thử.

## 1. WebGraphQlRequest là gì?

**WebGraphQlRequest** là đối tượng request ở tầng web của Spring for GraphQL. Nó kết hợp hai nhóm thông tin:

1. Nội dung GraphQL mà client gửi.
2. Thông tin HTTP/web transport đi kèm request.

Nhóm nội dung GraphQL được cung cấp qua hợp đồng request GraphQL cơ bản:

| Thành phần | Ý nghĩa |
|---|---|
| Document | GraphQL query, mutation hoặc subscription document |
| Operation name | Tên operation được chọn để thực thi nếu document có nhiều operation |
| Variables | Giá trị đầu vào cho các biến trong document |
| Extensions | Metadata mở rộng theo giao thức hoặc ứng dụng |

Nhóm thông tin web thường gồm:

| Thành phần | Ý nghĩa |
|---|---|
| Headers | HTTP headers như Authorization, Accept-Language hoặc X-Correlation-Id |
| URI | URI của endpoint nhận request |
| Remote address | Địa chỉ mạng của peer kết nối, nếu transport cung cấp |
| Attributes | Các thuộc tính gắn với web request theo adapter hoặc ứng dụng |

Ngoài việc đọc thông tin, WebGraphQlRequest còn cung cấp cơ chế cấu hình **ExecutionInput** để interceptor có thể bổ sung GraphQLContext hoặc điều chỉnh dữ liệu đầu vào execution trước khi GraphQL engine xử lý operation.

## 2. WebGraphQlRequest nằm ở đâu trong kiến trúc?

Một request HTTP điển hình được xử lý theo luồng:

~~~mermaid
flowchart TD
    A[HTTP client] --> B[Spring Web MVC hoặc WebFlux]
    B --> C[WebGraphQlHandler]
    C --> D[WebGraphQlInterceptor chain]
    D --> E[WebGraphQlRequest]
    E --> F[GraphQL execution input]
    F --> G[GraphQL engine]
    G --> H[DataFetcher / annotated controller]
    H --> I[Service và repository]
    I --> J[GraphQL response]
~~~

WebGraphQlRequest là ranh giới giữa web transport và GraphQL execution. Nó giúp interceptor truy cập HTTP details mà không cần controller tự phụ thuộc vào Servlet API hoặc WebFlux ServerWebExchange.

Các thành phần có vai trò khác nhau:

- **WebGraphQlRequest**: biểu diễn request và cung cấp thông tin transport cùng nội dung GraphQL.
- **WebGraphQlInterceptor**: xử lý request/response trước và sau GraphQL execution.
- **ExecutionInput**: đầu vào được GraphQL Java sử dụng để thực thi operation.
- **GraphQLContext**: nơi chia sẻ dữ liệu trong phạm vi execution.
- **DataFetcher/Controller**: resolve field theo schema và selection set.

Không nên xem WebGraphQlRequest là một service hoặc domain object. Nó là abstraction của tầng web.

## 3. Đọc nội dung GraphQL từ request

WebGraphQlRequest cung cấp các thông tin cốt lõi của GraphQL operation. Ví dụ, interceptor có thể kiểm tra operation name để áp dụng chính sách quan sát hoặc ghi log:

~~~java
@Component
public class OperationLoggingInterceptor implements WebGraphQlInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(OperationLoggingInterceptor.class);

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String operationName = request.getOperationName();

        log.debug("GraphQL operation received: {}", operationName);

        return chain.next(request);
    }
}
~~~

Các phương thức nội dung GraphQL thường dùng:

- getDocument() trả về document dạng chuỗi.
- getOperationName() trả về tên operation được client chọn, có thể không có.
- getVariables() trả về map variables.
- getExtensions() trả về map extensions.

Ví dụ đọc operation name và variables:

~~~java
String operationName = request.getOperationName();
Map<String, Object> variables = request.getVariables();
Map<String, Object> extensions = request.getExtensions();
~~~

### Khi nào cần đọc các giá trị này?

Một số use case hợp lý:

- Ghi operation name vào log hoặc metric.
- Kiểm tra extension do persisted query protocol sử dụng.
- Áp dụng giới hạn hoặc chính sách theo loại operation.
- Gắn thông tin chẩn đoán vào execution context.
- Điều tra request lỗi khi có correlation ID tương ứng.

Không nên ghi toàn bộ document và variables vào log theo mặc định. Variables có thể chứa thông tin cá nhân, access token hoặc dữ liệu nghiệp vụ nhạy cảm. Nếu cần chẩn đoán, hãy log operation name, correlation ID và những thuộc tính đã được chọn lọc.

## 4. Đọc HTTP headers

WebGraphQlRequest cung cấp headers dưới dạng cấu trúc HTTP của Spring. Interceptor có thể đọc một header bằng getFirst:

~~~java
@Component
public class ClientMetadataInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String clientVersion =
                request.getHeaders().getFirst("X-Client-Version");

        String correlationId =
                request.getHeaders().getFirst("X-Correlation-Id");

        return chain.next(request);
    }
}
~~~

Một số header thường gặp:

| Header | Mục đích |
|---|---|
| Authorization | Credential được gửi tới security infrastructure |
| Accept-Language | Ngôn ngữ client ưu tiên |
| X-Correlation-Id | Mã tương quan request nếu ứng dụng hỗ trợ |
| X-Client-Version | Phiên bản ứng dụng client |
| Content-Type | Kiểu nội dung request |
| Origin | Origin của trình duyệt, thường liên quan tới CORS |

Headers là dữ liệu đầu vào từ transport. Không phải header nào cũng đáng tin cậy. Ví dụ, client có thể tự đặt X-Tenant-Id; server cần xác định tenant từ principal hoặc nguồn đã được xác minh thay vì tin trực tiếp giá trị này.

### Header có thể thiếu hoặc có nhiều giá trị

Không nên giả định header luôn tồn tại:

~~~java
String clientVersion =
        request.getHeaders().getFirst("X-Client-Version");

if (!StringUtils.hasText(clientVersion)) {
    clientVersion = "unknown";
}
~~~

Với header có thể có nhiều giá trị, hãy dùng API phù hợp của HttpHeaders và quy định rõ cách chọn hoặc kết hợp giá trị. Không nên nối tùy tiện các giá trị có ý nghĩa khác nhau.

## 5. Đọc URI và remote address

WebGraphQlRequest cung cấp URI và thông tin remote address của request:

~~~java
@Override
public Mono<WebGraphQlResponse> intercept(
        WebGraphQlRequest request,
        Chain chain) {

    URI uri = request.getUri();
    InetSocketAddress remoteAddress = request.getRemoteAddress();

    log.debug(
            "GraphQL endpoint={}, remote={}",
            uri,
            remoteAddress);

    return chain.next(request);
}
~~~

URI hữu ích khi:

- Ứng dụng có nhiều GraphQL endpoint.
- Cần quan sát endpoint được gọi.
- Có quy tắc định tuyến hoặc phiên bản endpoint.
- Cần ghi lại thông tin transport trong log.

Remote address hữu ích cho chẩn đoán kết nối hoặc thống kê ở mức mạng. Tuy nhiên, địa chỉ này có thể là địa chỉ của reverse proxy, gateway hoặc load balancer thay vì địa chỉ thiết bị cuối của người dùng.

Nếu cần đọc forwarded headers như Forwarded hoặc X-Forwarded-For, chỉ nên tin chúng khi request đi qua proxy đã được cấu hình tin cậy. Client có thể tự gửi các header đó nếu hệ thống không lọc hoặc ghi đè ở gateway.

Không dùng remote address hoặc IP làm căn cứ duy nhất để xác thực người dùng hay cấp quyền truy cập dữ liệu.

## 6. Request attributes

WebGraphQlRequest có thể cung cấp các **request attributes** gắn với web request. Đây là nơi các thành phần ở tầng web có thể trao đổi dữ liệu phụ trợ theo request nếu adapter hoặc ứng dụng đã thiết lập những attribute đó.

Ví dụ đọc một attribute do thành phần web trước đó đặt:

~~~java
Object gatewayMetadata =
        request.getAttributes().get("gatewayMetadata");
~~~

Attributes khác với GraphQL variables và GraphQLContext:

| Loại dữ liệu | Mục đích |
|---|---|
| GraphQL variables | Đầu vào mà client gửi theo operation |
| Web request attributes | Dữ liệu gắn với request ở tầng web |
| GraphQLContext | Dữ liệu được chia sẻ trong quá trình GraphQL execution |

Không nên giả định một request attribute tự động xuất hiện trong GraphQLContext. Nếu resolver cần sử dụng giá trị đó, interceptor nên chuyển giá trị phù hợp vào ExecutionInput/GraphQLContext một cách tường minh.

Attributes cũng không nên trở thành nơi lưu state dùng chung giữa các request. Hãy giữ dữ liệu đúng phạm vi request và tránh đưa object web-specific sâu vào service layer.

## 7. Dùng WebGraphQlRequest trong WebGraphQlInterceptor

Một interceptor nhận WebGraphQlRequest và Chain. Interceptor có thể đọc request, cấu hình execution input rồi gọi chain.next(request) để chuyển tiếp.

Ví dụ đọc client version và correlation ID, sau đó đưa các giá trị đã chuẩn hóa vào GraphQLContext:

~~~java
@Component
public class ClientMetadataInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String clientVersion =
                request.getHeaders().getFirst("X-Client-Version");

        String correlationId =
                request.getHeaders().getFirst("X-Correlation-Id");

        if (!StringUtils.hasText(correlationId)) {
            correlationId = UUID.randomUUID().toString();
        }

        String normalizedVersion =
                StringUtils.hasText(clientVersion)
                        ? clientVersion.trim()
                        : "unknown";

        String requestId = correlationId;

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context -> {
                    context.put("clientVersion", normalizedVersion);
                    context.put("correlationId", requestId);
                }).build());

        return chain.next(request);
    }
}
~~~

Resolver có thể đọc context:

~~~java
@QueryMapping
public List<Book> books(
        @ContextValue("clientVersion") String clientVersion) {

    return bookService.findBooksForClientVersion(clientVersion);
}
~~~

Ví dụ chỉ minh họa cách truyền dữ liệu. Nếu client version chỉ phục vụ log hoặc metric, không cần đưa nó vào business service. Nếu metadata ảnh hưởng tới hành vi nghiệp vụ, cần xác định rõ contract và kiểm soát giá trị đầu vào.

### Vai trò của chain.next

chain.next(request) chuyển request sang interceptor tiếp theo hoặc tới GraphQL execution khi không còn interceptor nào.

Nếu interceptor không gọi chain.next, operation sẽ không tiếp tục theo chuỗi xử lý bình thường. Điều này chỉ phù hợp khi interceptor chủ động kết thúc request theo một cơ chế được thiết kế rõ ràng; không nên vô tình bỏ qua chain.

Vì phương thức interceptor trả về Mono<WebGraphQlResponse>, hãy giữ luồng xử lý reactive và tránh gọi block() trong interceptor.

## 8. configureExecutionInput thay đổi điều gì?

WebGraphQlRequest cung cấp configureExecutionInput để tùy chỉnh ExecutionInput trước khi GraphQL engine thực thi operation.

Ví dụ thêm GraphQLContext:

~~~java
request.configureExecutionInput((input, builder) ->
        builder.graphQLContext(context -> {
            context.put("tenantId", tenantId);
            context.put("correlationId", correlationId);
        }).build());
~~~

ExecutionInput là đối tượng đầu vào cho GraphQL Java. Ngoài context, tùy use case và API được Spring for GraphQL hỗ trợ, interceptor có thể điều chỉnh các thuộc tính execution phù hợp.

Nên dùng cấu hình này cho dữ liệu thực sự cần ở tầng GraphQL execution, ví dụ:

- Tenant đã được xác minh.
- Locale đã chuẩn hóa.
- Correlation ID.
- Principal hoặc thông tin actor phù hợp.
- Request-scoped service hoặc dữ liệu hỗ trợ resolver nếu có thiết kế rõ.

Không nên dùng ExecutionInput để nhét toàn bộ HTTP request hoặc toàn bộ headers vào context. Chỉ truyền những giá trị cần thiết, đã được kiểm tra và có kiểu dữ liệu rõ ràng.

### Giữ nguyên cấu hình đã có

Khi nhiều interceptor cùng gọi configureExecutionInput, mỗi interceptor nên chỉ bổ sung phần cấu hình mà nó sở hữu và tránh ghi đè context key của interceptor khác.

Nên thống nhất key qua hằng số:

~~~java
public final class GraphQlContextKeys {

    public static final String TENANT_ID = "tenantId";
    public static final String CORRELATION_ID = "correlationId";

    private GraphQlContextKeys() {
    }
}
~~~

Điều này giảm lỗi chính tả và giúp nhận biết key nào được dùng trong toàn ứng dụng.

## 9. WebGraphQlRequest khác HttpServletRequest và ServerWebExchange

Spring for GraphQL có thể chạy trên Spring MVC hoặc Spring WebFlux. Nếu controller phụ thuộc trực tiếp vào HttpServletRequest, code sẽ gắn với Servlet stack. Nếu phụ thuộc vào ServerWebExchange, code sẽ gắn với WebFlux.

WebGraphQlRequest cung cấp abstraction web phù hợp với Spring for GraphQL:

| Tiêu chí | WebGraphQlRequest | HttpServletRequest | ServerWebExchange |
|---|---|---|---|
| Mục đích | Request của GraphQL web transport | HTTP request trong Servlet | Request/response exchange trong WebFlux |
| Có GraphQL document/variables | Có qua GraphQL request contract | Không trực tiếp | Không trực tiếp |
| Truy cập HTTP headers | Có | Có | Có |
| Cấu hình GraphQL ExecutionInput | Có | Không | Không trực tiếp |
| Phụ thuộc transport cụ thể | Web abstraction của Spring GraphQL | Servlet | WebFlux |

Với logic GraphQL, ưu tiên WebGraphQlRequest trong interceptor. Với logic nghiệp vụ, không nên truyền cả ba loại request object vào service. Hãy chuyển thông tin cần thiết thành kiểu dữ liệu thuần Java.

## 10. WebGraphQlRequest và GraphQLContext khác nhau

Hai đối tượng phục vụ hai giai đoạn khác nhau:

- WebGraphQlRequest đại diện cho request ở tầng web.
- GraphQLContext đại diện cho context được chia sẻ trong quá trình GraphQL execution.

Luồng truyền dữ liệu:

~~~text
HTTP headers / URI / request attributes
                |
                v
        WebGraphQlRequest
                |
                v
      WebGraphQlInterceptor
                |
                v
       configureExecutionInput
                |
                v
          GraphQLContext
                |
                v
       @ContextValue / DataFetcher
~~~

Ví dụ:

~~~java
@QueryMapping
public List<Book> books(
        @ContextValue("tenantId") String tenantId) {

    return bookService.findBooks(tenantId);
}
~~~

Controller không cần nhận WebGraphQlRequest để đọc header. Interceptor đã chuyển tenant ID đã xác minh vào GraphQLContext.

Điều này làm rõ trách nhiệm:

- Interceptor hiểu HTTP request.
- GraphQLContext mang metadata của execution.
- Controller hiểu GraphQL field và input.
- Service hiểu use case và quy tắc nghiệp vụ.

## 11. Không dùng WebGraphQlRequest như nguồn dữ liệu tin cậy mặc định

WebGraphQlRequest phản ánh dữ liệu request mà server nhận được. Việc một giá trị có mặt trong request không làm nó trở thành đáng tin cậy.

Ví dụ:

~~~http
X-Tenant-Id: tenant-root
X-User-Role: ADMIN
X-Internal-Client: true
~~~

Client có thể tự đặt các header này nếu gateway không xóa hoặc kiểm soát. Không nên chuyển chúng thẳng vào GraphQLContext rồi dùng để phân quyền.

Quy tắc:

- Credential phải được Spring Security hoặc authentication infrastructure xác minh.
- Tenant phải được suy ra từ principal hoặc nguồn được tin cậy.
- Forwarded headers chỉ đáng tin khi được proxy tin cậy thiết lập.
- Correlation ID cần giới hạn độ dài và ký tự trước khi log.
- Client version chỉ nên dùng cho metric hoặc feature behavior sau khi kiểm tra định dạng.
- Không log Authorization header, cookie hoặc toàn bộ variables.

Nếu request chứa dữ liệu không hợp lệ, interceptor có thể từ chối request theo chính sách hoặc thay bằng giá trị server-side an toàn. Không nên để giá trị chưa xác minh đi vào service hoặc repository.

## 12. Một HTTP request có thể chứa thông tin gì ngoài operation?

Một request GraphQL qua HTTP thường có:

~~~http
POST /graphql
Content-Type: application/json
Accept: application/json
X-Correlation-Id: req-123
Accept-Language: vi-VN
Authorization: Bearer <token>
~~~

Body JSON có thể chứa:

~~~json
{
  "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
  "operationName": "FindBook",
  "variables": {
    "id": "book-01"
  },
  "extensions": {}
}
~~~

WebGraphQlRequest cung cấp cả nhóm thông tin GraphQL trong body và nhóm thông tin HTTP từ request. Điều này giúp interceptor có thể phối hợp:

- Operation name để quan sát loại operation.
- Variables để áp dụng giới hạn hoặc kiểm tra ở tầng giao thức khi cần.
- Headers để đọc locale, correlation ID hoặc thông tin client.
- URI để nhận biết endpoint.
- Remote address để hỗ trợ chẩn đoán mạng.

Không nên kiểm tra lại mọi quy tắc schema trong interceptor. GraphQL engine chịu trách nhiệm parse, validate document và coercion variables theo schema. Interceptor chỉ nên xử lý các chính sách request/transport phù hợp.

## 13. Xử lý lỗi và kết thúc request trong interceptor

Interceptor có thể gặp lỗi khi đọc hoặc xác thực metadata. Ví dụ, client gửi một client version sai định dạng hoặc request không đáp ứng chính sách.

Có hai hướng:

1. Từ chối request trước khi gọi chain.next nếu đây là lỗi transport/request-level.
2. Đưa thông tin đã xác minh vào execution context và để GraphQL execution/error handling xử lý lỗi ở cấp field hoặc operation nếu phù hợp.

Không nên tự tạo một GraphQL response không đúng cấu trúc hoặc nuốt exception rồi trả response thành công giả.

Khi cần dừng chuỗi interceptor, hãy dùng cơ chế response/error được Spring for GraphQL hỗ trợ trong phiên bản ứng dụng. Với lỗi GraphQL phát sinh trong resolver, nên sử dụng exception resolver hoặc GraphQL error handling phù hợp thay vì xử lý mọi trường hợp ở WebGraphQlRequest interceptor.

### Giữ nguyên tính reactive

WebGraphQlInterceptor trả Mono<WebGraphQlResponse>. Ví dụ xử lý bất đồng bộ:

~~~java
@Override
public Mono<WebGraphQlResponse> intercept(
        WebGraphQlRequest request,
        Chain chain) {

    return metadataService.lookupClientPolicy(request)
            .flatMap(policy -> {
                request.configureExecutionInput((input, builder) ->
                        builder.graphQLContext(context ->
                                context.put("clientPolicy", policy))
                            .build());

                return chain.next(request);
            });
}
~~~

Ví dụ giả định metadataService trả về Mono và việc tra cứu policy là cần thiết. Nếu dữ liệu có sẵn, xử lý đồng bộ đơn giản hơn. Tránh block() vì có thể chặn event loop trong WebFlux.

## 14. Kiểm thử WebGraphQlRequest và interceptor

Muốn kiểm thử headers, URI hoặc remote address đi qua web adapter, nên dùng integration test ở tầng HTTP. **HttpGraphQlTester** kết hợp WebTestClient cho phép gửi operation kèm headers.

Ví dụ:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebGraphQlRequestTest {

    @LocalServerPort
    int port;

    @Test
    void shouldPassRequestMetadataToGraphQlContext() {
        WebTestClient webClient = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .defaultHeader("X-Correlation-Id", "test-req-001")
                .defaultHeader("X-Client-Version", "2.4.0")
                .build();

        HttpGraphQlTester tester = HttpGraphQlTester.create(webClient);

        tester.document("""
                query {
                    requestInfo {
                        correlationId
                        clientVersion
                    }
                }
                """)
            .execute()
            .path("requestInfo.correlationId")
            .entity(String.class)
            .isEqualTo("test-req-001");
    }
}
~~~

Ví dụ giả định ứng dụng có field requestInfo phục vụ test hoặc nghiệp vụ. Không nên thêm field debug vào schema production chỉ để kiểm tra nội bộ.

Nên kiểm thử:

1. Document và operation name được đọc đúng.
2. Variables và extensions có giá trị như request gửi.
3. Header thiếu được xử lý theo fallback.
4. Header nhiều giá trị được xử lý đúng quy ước.
5. URI và remote address được đọc khi transport cung cấp.
6. Request attributes được sử dụng đúng phạm vi.
7. Interceptor chuyển metadata cần thiết vào GraphQLContext.
8. Resolver đọc được context bằng @ContextValue.
9. Metadata không bị chia sẻ giữa hai request đồng thời.
10. Header giả mạo tenant hoặc role không thể vượt qua authorization.
11. Interceptor tiếp tục chain đúng và không block reactive execution.
12. Variables hoặc headers nhạy cảm không xuất hiện trong log.

Nếu chỉ cần kiểm tra handler và GraphQLContext đã được cấu hình, có thể dùng tester ở execution layer. Nhưng test đó không xác nhận HTTP adapter và WebGraphQlInterceptor thực sự được gọi.

## 15. Những lỗi thường gặp khi làm việc với WebGraphQlRequest

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Header luôn null | Client không gửi, proxy xóa header hoặc sai tên | Kiểm tra request thực tế và header mapping |
| Context không có metadata | Chỉ đọc header nhưng không cấu hình ExecutionInput | Dùng configureExecutionInput |
| Resolver phụ thuộc HttpServletRequest | Đưa transport API vào controller/service | Đọc ở interceptor rồi chuyển vào GraphQLContext |
| Remote address không phải IP client | Request đi qua proxy/load balancer | Cấu hình trusted proxy và forwarded header policy |
| Operation name null | Client gửi anonymous operation hoặc không chọn tên | Xử lý giá trị optional |
| Log làm lộ dữ liệu | Ghi toàn bộ document, variables hoặc headers | Log metadata đã chọn lọc |
| Interceptor không chạy | Chưa đăng ký bean hoặc test không đi qua web transport | Kiểm tra cấu hình và dùng HttpGraphQlTester |
| Operation không tiếp tục | Quên gọi chain.next(request) | Tiếp tục chain hoặc kết thúc request có chủ đích |
| WebFlux bị chặn | Gọi block trong interceptor | Dùng reactive composition |
| Tenant bị giả mạo | Tin trực tiếp header do client gửi | Suy tenant từ authentication đã xác minh |
| Nhiều interceptor ghi đè context key | Không thống nhất key và quyền sở hữu | Dùng hằng số và phân chia trách nhiệm |

## 16. Quy trình sử dụng WebGraphQlRequest

Khi cần xử lý request metadata hoặc thông tin transport:

1. Xác định thông tin cần đọc thuộc GraphQL operation hay HTTP transport.
2. Dùng WebGraphQlRequest trong WebGraphQlInterceptor để đọc document, operation name, variables, extensions hoặc HTTP details.
3. Chọn headers, URI, remote address và attributes đúng với use case.
4. Kiểm tra giá trị thiếu, định dạng và trust boundary.
5. Không dùng header hoặc remote address làm bằng chứng xác thực nếu chưa được xác minh.
6. Chuyển những giá trị cần cho resolver vào GraphQLContext qua configureExecutionInput.
7. Dùng @ContextValue hoặc DataFetchingEnvironment để đọc trong GraphQL handler.
8. Chuyển dữ liệu cần thiết thành request context hoặc command thuần Java trước khi gọi service.
9. Gọi chain.next(request) để tiếp tục xử lý và giữ tính reactive.
10. Kiểm thử qua HttpGraphQlTester nếu cần xác nhận hành vi của web transport.
11. Giới hạn logging để không ghi credential hoặc variables nhạy cảm.

WebGraphQlRequest là điểm truy cập thống nhất tới GraphQL payload và thông tin web request trong Spring for GraphQL. Nó giúp WebGraphQlInterceptor đọc document, operation, variables, extensions, headers, URI, remote address và request attributes trước khi GraphQL engine thực thi. Khi cần chia sẻ metadata cho resolver, interceptor nên cấu hình ExecutionInput và GraphQLContext thay vì để controller phụ thuộc trực tiếp vào HTTP API. Giữ rõ ranh giới giữa transport, execution và service giúp request metadata dễ kiểm soát, an toàn và thuận tiện kiểm thử.
