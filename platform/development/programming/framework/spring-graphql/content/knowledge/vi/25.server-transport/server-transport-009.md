# HTTP status cho lỗi transport trong Spring for GraphQL

GraphQL được thiết kế độc lập với HTTP, nhưng phần lớn ứng dụng Spring for GraphQL vẫn nhận request qua HTTP. Vì vậy, một lỗi có thể được thể hiện ở hai nơi khác nhau: HTTP status của transport và trường errors trong GraphQL response.

HTTP status mô tả kết quả xử lý request ở tầng HTTP/transport, chẳng hạn request body không đọc được, thiếu thông tin xác thực, media type không được hỗ trợ hoặc server timeout. GraphQL errors mô tả lỗi trong quá trình parse, validation hoặc thực thi operation. Hai lớp này có liên quan nhưng không thay thế cho nhau.

Trong Spring for GraphQL, cần đặc biệt chú ý media type mà client gửi trong Accept header. application/json giữ hành vi tương thích cũ; application/graphql-response+json cho phép server dùng HTTP 4xx cho một số GraphQL request errors trước execution. Sau khi request đã được validation thành công, tài liệu Spring for GraphQL 2.1.0 mô tả HTTP status là 200 và lỗi thực thi nằm trong trường errors của response.

## 1. Phân biệt HTTP status và GraphQL errors

Một request GraphQL qua HTTP đi qua nhiều bước:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[HTTP method / headers / body]
    B --> C{Transport request hợp lệ?}
    C -->|Không| D[HTTP 4xx hoặc 5xx]
    C -->|Có| E[Parse GraphQL document]
    E --> F{Parse và validation thành công?}
    F -->|Không| G[GraphQL request errors]
    F -->|Có| H[GraphQL execution]
    H --> I{Resolver có lỗi?}
    I -->|Không| J[HTTP response + data]
    I -->|Có| K[HTTP response + data/errors]
~~~

Có thể nhìn các trường hợp như sau:

| Loại lỗi | Ví dụ | Nơi thể hiện thường gặp |
| --- | --- | --- |
| HTTP/transport error | JSON body sai cú pháp, Content-Type không hỗ trợ, thiếu credential | HTTP status 4xx/5xx; body có thể không phải GraphQL response. |
| GraphQL request error | Document sai cú pháp, field không tồn tại, argument không hợp lệ | GraphQL response có errors; HTTP status phụ thuộc media type và behavior của Spring. |
| GraphQL execution error | Resolver gọi database thất bại, không tìm thấy dữ liệu, field bị từ chối | GraphQL response có errors và có thể có data một phần; Spring thường trả HTTP 200 sau validation. |
| Client/connection error | DNS lỗi, TLS lỗi, socket bị đóng | Client không nhận được GraphQL response hợp lệ; không có HTTP status từ GraphQL handler nếu chưa nhận được response. |

Ví dụ một query có thể thực thi nhưng một field thất bại:

~~~json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Không thể tải sách",
      "path": ["book"]
    }
  ]
}
~~~

Đây là GraphQL execution error. Với behavior được mô tả trong Spring for GraphQL 2.1.0, HTTP response vẫn là 200 OK vì GraphQL request đã qua bước validation và đi vào execution.

Ngược lại, nếu request body không phải JSON hợp lệ, GraphQL engine chưa nhận được một GraphQL request có thể thực thi. Đây là lỗi ở tầng HTTP request decoding và thường được trả bằng HTTP 400 Bad Request.

## 2. Vai trò của GraphQlHttpHandler

Spring for GraphQL cung cấp GraphQlHttpHandler cho HTTP transport. Có hai biến thể tương ứng với Spring MVC và Spring WebFlux. Cả hai xử lý request bất đồng bộ; khác biệt chính nằm ở cách ghi HTTP response.

GraphQlHttpHandler nhận GraphQL request, chuyển request qua WebGraphQlHandler/interceptor chain rồi tới ExecutionGraphQlService để thực thi GraphQL Java. Spring Boot GraphQL starter tự cấu hình endpoint này trong ứng dụng thông thường.

Theo cấu hình mặc định:

- HTTP POST được bật.
- Content-Type của request là application/json.
- Request body chứa document GraphQL cùng operationName, variables và extensions nếu có.
- Response media type ưu tiên là application/graphql-response+json.
- Client cũ có thể yêu cầu application/json để dùng hành vi HTTP tương thích cũ.

Một POST request ví dụ:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/graphql-response+json, application/json;q=0.9

{
  "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
  "variables": {
    "id": "book-10"
  }
}
~~~

Không nên tự viết controller REST để parse body rồi gọi GraphQL Java nếu ứng dụng đã dùng GraphQlHttpHandler. Handler đã quản lý content negotiation, request decoding, execution và response serialization theo tích hợp Spring for GraphQL.

## 3. Ảnh hưởng của Accept và response media type

Accept header cho server biết client có thể đọc loại response nào. Spring for GraphQL hỗ trợ hai media type quan trọng:

| Response media type | Ý nghĩa |
| --- | --- |
| application/graphql-response+json | Media type dành riêng cho GraphQL response, hỗ trợ behavior theo GraphQL over HTTP. |
| application/json | Media type truyền thống, được giữ để tương thích với client cũ. |

Client có thể gửi:

~~~http
Accept: application/graphql-response+json, application/json;q=0.9
~~~

Cách này ưu tiên media type GraphQL chuyên biệt, nhưng vẫn cho phép fallback về application/json nếu server hoặc môi trường cũ chưa hỗ trợ media type mới.

Tài liệu Spring for GraphQL 2.1.0 mô tả behavior như sau:

- Nếu server không khả dụng, credential bị thiếu hoặc request body không phải JSON hợp lệ, client có thể nhận HTTP 4xx/5xx.
- Nếu Accept là application/graphql-response+json, GraphQL document không parse được hoặc không hợp lệ theo GraphQL engine sẽ nhận HTTP 4xx.
- Nếu Accept là application/json, cùng lỗi parse/validation GraphQL vẫn dùng HTTP 200 để tương thích legacy.
- Khi GraphQL request đã được validation thành công, HTTP status luôn là 200; lỗi phát sinh trong execution được đưa vào errors.

Điều này có nghĩa hai client gửi cùng một GraphQL document sai nhưng dùng Accept khác nhau có thể quan sát HTTP status khác nhau, dù lỗi GraphQL trong body cùng bản chất.

## 4. Các HTTP status thường gặp

Bảng dưới đây phân biệt status thường thấy ở Spring GraphQL với status do web server, security filter hoặc gateway tạo ra. Không phải mọi status trong bảng đều do GraphQlHttpHandler trực tiếp sinh ra.

| HTTP status | Ý nghĩa | Tình huống thường gặp |
| --- | --- | --- |
| 200 OK | HTTP exchange thành công | Query/mutation đã qua validation; có thể vẫn có GraphQL errors trong body. |
| 400 Bad Request | Request không đọc hoặc không phân tích được | JSON body sai cú pháp hoặc request HTTP không hợp lệ. |
| 401 Unauthorized | Chưa xác thực hoặc credential không hợp lệ | Spring Security chặn request trước khi GraphQL execution. |
| 403 Forbidden | Đã xác thực nhưng không được phép truy cập endpoint | Security policy ở tầng HTTP từ chối request. |
| 405 Method Not Allowed | HTTP method hoặc operation không được phép qua method đó | Mutation được gửi bằng GET khi GET transport đã bật; handler từ chối method và trả Allow header. |
| 406 Not Acceptable | Không có response media type phù hợp | Handler không thể đáp ứng Accept header và chọn từ chối content negotiation. |
| 408 Request Timeout | GraphQL web request mất quá thời hạn cấu hình để tạo response | TimeoutWebGraphQlInterceptor dùng status mặc định này. |
| 413 Content Too Large | Request body vượt giới hạn | Web server, reverse proxy hoặc gateway từ chối body quá lớn. |
| 415 Unsupported Media Type | Content-Type request không được hỗ trợ | Client gửi text/plain thay vì application/json. |
| 429 Too Many Requests | Client vượt rate limit | API gateway, filter hoặc rate limiter từ chối request. |
| 500 Internal Server Error | Server gặp lỗi không thể xử lý | Lỗi hạ tầng hoặc exception không được xử lý ở tầng HTTP. |
| 503 Service Unavailable | Server tạm thời không thể nhận request | Maintenance, load shedding hoặc dependency/hạ tầng không sẵn sàng. |

Các status 401, 403, 413, 429, 500 và 503 thường do tầng bảo mật hoặc hạ tầng web quyết định. Không nên giả định mọi lỗi resolver đều biến thành HTTP 500; GraphQL execution errors thường được biểu diễn trong response body.

## 5. Request errors và behavior của hai media type

GraphQL request error xảy ra trước khi operation bắt đầu thực thi, ví dụ:

- Document không parse được.
- Query tham chiếu field không tồn tại trong schema.
- Argument hoặc variable không phù hợp với định nghĩa operation.
- Không xác định được operation cần chạy khi document chứa nhiều operation nhưng thiếu operationName.

Ví dụ document không hợp lệ:

~~~graphql
query {
    unknownBookField
}
~~~

Với Accept là application/graphql-response+json, Spring for GraphQL 2.1.0 trả HTTP 4xx cho loại request error này. Tài liệu transport mô tả status theo nhóm 4xx; status cụ thể cần được xác nhận theo loại lỗi và phiên bản handler. Body GraphQL có thể có dạng:

~~~json
{
  "data": null,
  "errors": [
    {
      "message": "Cannot query field 'unknownBookField' on type 'Query'."
    }
  ]
}
~~~

Response vẫn khai báo media type GraphQL:

~~~http
Content-Type: application/graphql-response+json
~~~

Điểm cần nhớ theo tài liệu Spring là nhóm lỗi này dùng 4xx với application/graphql-response+json.

Nếu client yêu cầu application/json, Spring giữ behavior legacy và trả HTTP 200 cho lỗi parse/validation GraphQL:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "data": null,
  "errors": [
    {
      "message": "Cannot query field 'unknownBookField' on type 'Query'."
    }
  ]
}
~~~

Body vẫn chứa GraphQL errors. Vì vậy, client dùng application/json không thể chỉ dựa vào HTTP 200 để kết luận operation hợp lệ hoặc thành công.

## 6. Execution errors thường không đổi HTTP status

Sau khi document parse và validation thành công, GraphQL engine bắt đầu thực thi. Nếu một resolver ném exception, Spring for GraphQL thường đưa lỗi vào errors trong GraphQL response.

Ví dụ resolver:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

Nếu exception được ánh xạ thành GraphQL error, response có thể như sau:

~~~http
HTTP/1.1 200 OK
Content-Type: application/graphql-response+json

{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Không tìm thấy sách",
      "path": ["book"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

HTTP 200 ở đây không có nghĩa mọi field đều thành công. Nó cho biết HTTP request đã được xử lý và GraphQL execution đã diễn ra. Client phải đọc cả data lẫn errors.

Nếu field nullable, GraphQL có thể trả null ở field bị lỗi và giữ các field khác. Nếu field hoặc parent được khai báo Non-Null, null propagation có thể làm phần data lớn hơn bị null. Đây vẫn là execution error, không tự động biến thành HTTP 500 trong behavior Spring được mô tả.

## 7. Lưu ý về GraphQL over HTTP specification mới

GraphQL over HTTP có bản September 2026. Bản này khuyến nghị status 294 Partial Success khi GraphQL result có cả data và errors; request error result không có data thì dùng status 4xx hoặc 5xx phù hợp.

Tuy nhiên, tài liệu Spring for GraphQL 2.1.0 hiện mô tả behavior rằng sau khi GraphQL request đã được validation thành công, HTTP response status luôn là 200, kể cả khi execution có errors. Vì vậy:

- Đừng giả định Spring for GraphQL 2.1 tự động trả 294.
- Hãy kiểm tra behavior của phiên bản Spring for GraphQL thực tế mà ứng dụng đang dùng.
- Nếu hệ thống cần tuân thủ một phiên bản GraphQL over HTTP cụ thể, hãy kiểm thử status và response media type trên handler thực tế.
- Không tự đổi mọi execution error thành 4xx/5xx chỉ để làm dashboard HTTP trông giống REST; điều đó có thể khiến client hiểu nhầm partial GraphQL result là transport failure.

Sự khác biệt này quan trọng khi nâng cấp framework, client, gateway hoặc tiêu chuẩn API. Tài liệu Spring và phiên bản specification mà hệ thống triển khai cần được đối chiếu với nhau.

## 8. Lỗi xác thực và phân quyền ở hai tầng

Cần phân biệt quyền truy cập endpoint với quyền truy cập một field hoặc tài nguyên cụ thể.

### Xác thực ở HTTP security layer

Spring Security có thể chặn request trước khi GraphQL engine chạy:

- Không có credential hoặc token không hợp lệ: thường là 401 Unauthorized.
- Người dùng đã xác thực nhưng không được phép truy cập endpoint: thường là 403 Forbidden.

Trong các trường hợp này, client có thể nhận HTTP error response từ security filter. GraphQL resolver chưa chắc đã được gọi.

### Authorization trong GraphQL execution

Một người dùng có thể truy cập endpoint nhưng không được đọc một field hoặc một tài nguyên cụ thể. Khi đó, ứng dụng có thể kiểm tra quyền trong service, method security hoặc data fetcher.

Ví dụ:

~~~java
@QueryMapping
public Book privateBook(@Argument("id") String id, Principal principal) {
    return bookService.findVisibleBook(id, principal.getName())
            .orElseThrow(() -> new AccessDeniedException("Access denied"));
}
~~~

Nếu exception được xử lý trong GraphQL execution, kết quả thường là GraphQL errors trong response HTTP 200 theo behavior Spring sau validation. Đây là authorization theo field/resource, khác với việc security filter chặn toàn bộ HTTP request.

Không nên dùng HTTP status để thay thế kiểm tra quyền ở từng field. Một GraphQL operation có thể chọn nhiều field, trong đó một số field được phép và một số field bị từ chối.

## 9. HTTP method và status khi dùng GET

GraphQlHttpHandler chỉ bật POST theo mặc định. Có thể bật GET nếu ứng dụng thực sự cần, nhưng phải cấu hình cả handler lẫn route predicate.

Ví dụ:

~~~java
GraphQlHttpHandler httpHandler =
        GraphQlHttpHandler.builder(webGraphQlHandler)
                .httpMethods(HttpMethod.GET, HttpMethod.POST)
                .build();

RequestPredicate predicate =
        GraphQlRequestPredicates.graphQlHttp(
                "/graphql", Set.of(HttpMethod.GET, HttpMethod.POST));
~~~

GET chỉ dành cho operation an toàn như query. Mutation không được thực thi qua GET vì GET được kỳ vọng không tạo side effect.

Nếu client gửi mutation qua GET, Spring trả 405 Method Not Allowed cùng Allow header liệt kê các method endpoint chấp nhận.

Trước khi bật GET, cần cân nhắc:

- Query string và variables có thể xuất hiện trong access log, browser history, Referer header và proxy/cache.
- Không gửi password, token hoặc dữ liệu nhạy cảm trong query string.
- GET là CORS simple request trong nhiều trường hợp; cần hiểu tác động của cookie và CSRF.
- Query vẫn có thể tiêu tốn tài nguyên và cần rate limit, audit, complexity/depth limit.

POST phù hợp hơn cho mutation và request có variables nhạy cảm.

## 10. Timeout HTTP bằng TimeoutWebGraphQlInterceptor

Spring for GraphQL cung cấp TimeoutWebGraphQlInterceptor để giới hạn thời gian xử lý request ở web transport. Constructor chỉ nhận Duration sẽ dùng HTTP 408 Request Timeout theo mặc định. Có overload cho phép chọn status khác.

Cấu hình Spring Boot:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.TimeoutWebGraphQlInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(Duration.ofSeconds(5));
    }
}
~~~

Nếu muốn chọn status khác cho timeout, có thể dùng constructor có tham số HttpStatus trong phiên bản hỗ trợ:

Thay bean ở ví dụ trước bằng cấu hình sau nếu muốn dùng 503; không cần đăng ký đồng thời cả hai timeout bean cho cùng một handler.

~~~java
@Bean
TimeoutWebGraphQlInterceptor timeoutWithServiceUnavailable() {
    return new TimeoutWebGraphQlInterceptor(
            Duration.ofSeconds(5), HttpStatus.SERVICE_UNAVAILABLE);
}
~~~

Ví dụ này cần import org.springframework.http.HttpStatus. Hãy chọn status phù hợp với contract của API; 408 thường phù hợp với request timeout, còn 503 biểu thị server tạm thời không thể phục vụ request.

Timeout interceptor gửi tín hiệu cancel lên chain khi hết thời gian. Các reactive data fetcher có thể nhận cancellation và dừng công việc đang chạy. Điều này giúp tránh tiếp tục giữ tài nguyên cho một response mà client không còn chờ.

Với streaming response như subscription, timeout này chỉ áp dụng đến khi response stream được thiết lập. Sau đó cần cấu hình timeout riêng trên transport handler như WebSocket hoặc SSE nếu nghiệp vụ yêu cầu.

TimeoutWebGraphQlInterceptor không thay thế timeout của reverse proxy, load balancer, database hoặc HTTP client gọi dịch vụ khác. Các timeout cần được phối hợp để tránh gateway đóng kết nối trước khi ứng dụng tự xử lý timeout.

## 11. Request-level errors và WebGraphQlInterceptor

Request errors như parse/validation failure xảy ra trước khi data fetcher được gọi. Vì vậy DataFetcherExceptionResolver không xử lý được các lỗi global này.

Spring for GraphQL cho phép dùng WebGraphQlInterceptor để quan sát hoặc biến đổi ExecutionResult sau khi GraphQL engine xử lý request:

~~~java
import java.util.List;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import reactor.core.publisher.Mono;

class RequestErrorInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        return chain.next(request).map(response -> {
            if (response.isValid()) {
                return response;
            }

            List<GraphQLError> errors = response.getErrors().stream()
                    .map(error -> GraphqlErrorBuilder.newError()
                            .message("GraphQL request không hợp lệ")
                            .build())
                    .toList();

            return response.transform(builder ->
                    builder.errors(errors).build());
        });
    }
}
~~~

Ví dụ trên minh họa cách chuẩn hóa request errors. Trong ứng dụng thực tế, cần cân nhắc giữ lại thông tin hữu ích cho developer như vị trí lỗi hoặc mã lỗi, đồng thời không đưa dữ liệu nhạy cảm ra client.

Interceptor biến đổi GraphQL ExecutionResult; điều đó không có nghĩa nó tùy ý đặt HTTP status. HTTP status vẫn do transport handler và các quy tắc của media type quyết định. Nếu cần thay đổi status cho timeout, dùng timeout interceptor hoặc cơ chế transport phù hợp thay vì cố gán ErrorType cho GraphQL error.

## 12. ErrorType không phải HTTP status

Spring for GraphQL có ErrorType như BAD_REQUEST, UNAUTHORIZED, FORBIDDEN, NOT_FOUND và INTERNAL_ERROR. Đây là classification của GraphQL error, không phải đối tượng HttpStatus.

Ví dụ:

~~~java
GraphqlErrorBuilder.newError()
        .message("Bạn không có quyền xem sách này")
        .errorType(ErrorType.FORBIDDEN)
        .build();
~~~

ErrorType.FORBIDDEN giúp client hiểu loại lỗi trong GraphQL response. Nó không tự động buộc GraphQlHttpHandler trả HTTP 403 cho toàn bộ request.

Tương tự, ErrorType.NOT_FOUND không đồng nghĩa HTTP 404. Một field không tìm thấy tài nguyên có thể trả null hoặc GraphQL error trong HTTP 200. HTTP 404 thường mô tả endpoint hoặc resource ở tầng HTTP không tồn tại, không phải mọi entity GraphQL không tìm thấy.

## 13. Client nên đọc status và body theo thứ tự nào?

Client cần kiểm tra cả HTTP status, Content-Type và GraphQL response body.

Một quy trình xử lý hợp lý:

1. Nếu không có HTTP response do DNS/TLS/socket failure, xử lý như lỗi kết nối.
2. Nếu response là 4xx/5xx, đọc Content-Type trước khi giả định body là GraphQL JSON.
3. Nếu Content-Type là application/graphql-response+json, có thể parse body theo GraphQL response contract ngay cả khi status không phải 2xx.
4. Nếu Content-Type là application/json, lưu ý lỗi 4xx/5xx có thể đến từ gateway, reverse proxy hoặc security middleware.
5. Nếu body là GraphQL response, kiểm tra errors và data; không chỉ kiểm tra HTTP 200.
6. Phân biệt lỗi có thể retry như timeout/503 với lỗi không nên retry như validation, authentication hoặc forbidden.

Ví dụ client HTTP:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/graphql-response+json, application/json;q=0.9

{
  "query": "{ book(id: \"missing\") { id title } }"
}
~~~

Khi nhận response, ứng dụng nên kiểm tra:

- Status code: request ở tầng HTTP có được chấp nhận không?
- Content-Type: body có phải GraphQL response không?
- errors: có lỗi request hoặc execution nào không?
- data: có dữ liệu đầy đủ hay một phần không?
- extensions: có mã lỗi hoặc metadata đã được server công khai không?

Không nên retry mọi response 200 có errors. Một số lỗi là lỗi nghiệp vụ cố định như NOT_FOUND hoặc FORBIDDEN; retry không giúp ích. Cũng không nên retry mọi 5xx vô hạn vì có thể làm tăng tải khi server đang quá tải.

## 14. Kiểm thử HTTP status bằng WebTestClient

GraphQlTester phù hợp để kiểm thử GraphQL execution, nhưng nếu mục tiêu là xác minh HTTP status, Content-Type và HTTP headers, hãy kiểm thử qua HTTP handler. Với Spring WebFlux, có thể dùng WebTestClient; với Spring MVC có thể dùng MockMvc hoặc WebTestClient được cấu hình tương ứng.

Ví dụ kiểm thử execution error vẫn là HTTP 200:

~~~java
@Test
void executionErrorIsReturnedInGraphQlBody() {
    webTestClient.post()
            .uri("/graphql")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.parseMediaType(
                    "application/graphql-response+json"))
            .bodyValue(Map.of(
                    "query",
                    "{ book(id: \"missing\") { id title } }"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                    MediaType.parseMediaType(
                            "application/graphql-response+json"))
            .expectBody()
            .jsonPath("$.errors").exists();
}
~~~

Ví dụ kiểm thử GraphQL validation error với media type mới:

~~~java
@Test
void invalidDocumentUsesClientErrorWithGraphQlResponseJson() {
    webTestClient.post()
            .uri("/graphql")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.parseMediaType(
                    "application/graphql-response+json"))
            .bodyValue(Map.of("query", "{ unknownBookField }"))
            .exchange()
            .expectStatus().is4xxClientError()
            .expectHeader().contentTypeCompatibleWith(
                    MediaType.parseMediaType(
                            "application/graphql-response+json"))
            .expectBody()
            .jsonPath("$.errors").exists();
}
~~~

Ví dụ kiểm thử behavior legacy:

~~~java
@Test
void invalidDocumentWithLegacyJsonUsesOkStatus() {
    webTestClient.post()
            .uri("/graphql")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("query", "{ unknownBookField }"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.errors").exists();
}
~~~

Các test giả định endpoint /graphql, WebTestClient và schema đã được cấu hình; query book có thể thực thi và query unknownBookField không hợp lệ. Status 4xx cụ thể của request error cần được kiểm tra theo Spring for GraphQL version đang dùng.

Ngoài ra, nên có test cho:

- Request body sai JSON trả 400.
- Content-Type không hỗ trợ trả 415.
- Endpoint từ chối credential trả 401/403 theo security policy.
- GET mutation trả 405 và có Allow header khi GET được bật.
- Timeout interceptor trả 408 theo mặc định.
- Query execution có một field lỗi vẫn có HTTP 200 theo behavior Spring 2.1.
- Request Accept không tương thích được xử lý đúng theo content negotiation.
- Reverse proxy hoặc gateway không thay đổi sai Content-Type và status của GraphQL response.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Thấy HTTP 200 nhưng query có errors | GraphQL execution error được đưa vào body | Đọc errors và data thay vì chỉ kiểm tra status. |
| Client cũ nhận 200 cho document sai | Client yêu cầu application/json theo legacy behavior | Ưu tiên application/graphql-response+json nếu client hỗ trợ. |
| Client coi HTTP 4xx là body HTML | Gateway/security middleware trả lỗi trước GraphQL handler | Kiểm tra Content-Type và nguồn response trước khi parse. |
| Resolver ném lỗi nhưng không thấy HTTP 500 | Execution errors không tự chuyển thành HTTP 5xx | Xử lý GraphQL errors trong body theo contract. |
| ErrorType.FORBIDDEN nhưng HTTP vẫn 200 | ErrorType là GraphQL classification, không phải HttpStatus | Tách field authorization khỏi endpoint-level security. |
| Timeout không trả status mong muốn | Chưa cấu hình TimeoutWebGraphQlInterceptor hoặc timeout tầng proxy đến trước | Cấu hình interceptor và đồng bộ timeout giữa các tầng. |
| Mutation chạy qua GET bị từ chối | GET là safe method và không được thực thi mutation | Dùng POST cho mutation. |
| Client retry vô hạn | Không phân loại transport error, request error và business error | Chỉ retry lỗi tạm thời, giới hạn số lần và dùng backoff. |
| Test GraphQlTester pass nhưng HTTP status sai | Test chỉ kiểm tra execution, không kiểm tra transport | Dùng WebTestClient hoặc MockMvc cho HTTP behavior. |

## 16. Checklist thiết kế HTTP status cho GraphQL

1. Phân biệt transport errors, GraphQL request errors và GraphQL execution errors.
2. Dùng POST với Content-Type application/json cho request mặc định.
3. Gửi Accept application/graphql-response+json nếu client hỗ trợ.
4. Duy trì application/json khi cần tương thích client cũ.
5. Đọc cả HTTP status, Content-Type, data và errors ở client.
6. Dùng Spring Security cho authentication và endpoint-level authorization.
7. Dùng GraphQL error classification cho lỗi theo field/resource; đừng nhầm ErrorType với HTTP status.
8. Cấu hình TimeoutWebGraphQlInterceptor nếu cần giới hạn thời gian xử lý request.
9. Bật GET chỉ khi có lý do rõ ràng và hiểu các rủi ro của query string.
10. Không ép mọi GraphQL execution error thành HTTP 4xx/5xx.
11. Kiểm thử status và media type qua HTTP handler thực tế.
12. Đối chiếu behavior của phiên bản Spring for GraphQL với phiên bản GraphQL over HTTP mà hệ thống cam kết hỗ trợ.

HTTP status cho biết request đã đi qua tầng transport như thế nào; GraphQL errors giải thích vấn đề trong document hoặc quá trình thực thi operation. Spring for GraphQL dùng content negotiation để cân bằng behavior mới với tương thích cũ. Khi phân loại đúng lỗi, cấu hình timeout và security ở đúng tầng, đồng thời kiểm thử cả HTTP status lẫn GraphQL body, client và hạ tầng quan sát sẽ hiểu chính xác tình trạng API.

Tài liệu tham khảo:
- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Request Execution and Timeout](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [TimeoutWebGraphQlInterceptor API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/server/TimeoutWebGraphQlInterceptor.html)
- [GraphQL over HTTP — September 2026](https://http-spec.graphql.org/September2026/)
