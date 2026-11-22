# HTTP GraphQL transport

## Mục tiêu

Sau bài học này, bạn có thể:

- Mô tả đường đi của một GraphQL request qua HTTP trong Spring for GraphQL.
- Cấu hình endpoint HTTP bằng Spring Boot.
- Phân biệt POST và GET, hiểu giới hạn của từng phương thức.
- Đọc và tạo request payload với `query`, `operationName`, `variables` và `extensions`.
- Hiểu vai trò của Content-Type, Accept và response media type.
- Phân biệt cách triển khai trên Spring MVC và Spring WebFlux.
- Dùng `WebGraphQlInterceptor` để bổ sung metadata vào GraphQL execution context.
- Tích hợp HTTP transport với security, CORS, giới hạn request và observability.
- Kiểm thử endpoint HTTP bằng `HttpGraphQlTester`.

## 1. HTTP GraphQL transport là gì?

GraphQL định nghĩa ngôn ngữ query, schema và cách thực thi operation. HTTP GraphQL transport quy định cách client gửi operation tới server và nhận kết quả qua HTTP.

Trong ứng dụng Spring for GraphQL, client thường gửi request đến một endpoint duy nhất, ví dụ `/graphql`. Endpoint này có thể tiếp nhận nhiều loại operation:

- Query để đọc dữ liệu.
- Mutation để thay đổi dữ liệu.

Subscription cần một transport hỗ trợ streaming như WebSocket hoặc RSocket. HTTP request-response thông thường trả về một response cho mỗi request nên không phù hợp để giữ một luồng event dài hạn.

Ví dụ client gửi Query:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    id
    title
  }
}
~~~

Server thực thi operation theo schema và trả về một JSON response:

~~~json
{
  "data": {
    "book": {
      "id": "b-01",
      "title": "GraphQL in Practice"
    }
  }
}
~~~

HTTP transport chịu trách nhiệm nhận request, chuyển nội dung sang GraphQL execution và ghi kết quả ra HTTP response. Nó không thay thế schema, resolver hoặc service nghiệp vụ.

## 2. Luồng xử lý HTTP trong Spring for GraphQL

Spring for GraphQL tách phần thực thi GraphQL khỏi lớp web transport. Một request HTTP đi qua các thành phần chính:

~~~mermaid
flowchart TD
    A[GraphQL client] --> B[HTTP endpoint /graphql]
    B --> C[GraphQlHttpHandler]
    C --> D[WebGraphQlHandler]
    D --> E[WebGraphQlInterceptor chain]
    E --> F[ExecutionGraphQlService]
    F --> G[GraphQL Java engine]
    G --> H[DataFetcher / annotated controller]
    H --> I[Service and repository]
    I --> G
    G --> J[GraphQL response]
    J --> C
    C --> K[HTTP response]
~~~

Vai trò từng lớp:

| Thành phần | Trách nhiệm |
|---|---|
| HTTP endpoint | Nhận request tại URL được cấu hình |
| `GraphQlHttpHandler` | Adapter giữa HTTP và GraphQL handler |
| `WebGraphQlHandler` | Xử lý request ở tầng Spring GraphQL và chạy interceptor chain |
| `WebGraphQlInterceptor` | Bổ sung metadata, kiểm tra hoặc biến đổi request/response |
| `ExecutionGraphQlService` | Điều phối việc thực thi GraphQL |
| GraphQL Java | Validate operation, resolve field và tạo ExecutionResult |
| Controller/DataFetcher | Cung cấp dữ liệu cho từng field |

Spring Boot tự cấu hình các thành phần HTTP transport khi có starter phù hợp. Ứng dụng thường chỉ cần khai báo schema, controller và cấu hình endpoint.

## 3. Cấu hình HTTP endpoint trong Spring Boot

Với Spring Boot, endpoint HTTP GraphQL mặc định thường là `/graphql`. Có thể thay đổi bằng thuộc tính `spring.graphql.path`.

Ví dụ:

~~~yaml
spring:
  graphql:
    path: /api/graphql
~~~

Khi ứng dụng khởi động, client gửi request đến:

~~~text
http://localhost:8080/api/graphql
~~~

Nếu không khai báo `spring.graphql.path`, endpoint mặc định là:

~~~text
http://localhost:8080/graphql
~~~

Spring Boot hỗ trợ tích hợp Spring for GraphQL trên cả hai web stack:

- Spring MVC dựa trên Servlet API.
- Spring WebFlux dựa trên reactive web stack.

Hãy dùng starter và web stack phù hợp với ứng dụng. Không cần tự tạo một controller REST chỉ để nhận JSON GraphQL nếu auto-configuration đã cung cấp HTTP handler.

Ví dụ dependencies Maven thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-graphql</artifactId>
</dependency>

<!-- Chọn một web stack phù hợp với ứng dụng -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Nếu ứng dụng dùng WebFlux, dùng `spring-boot-starter-webflux` thay cho starter MVC. Không nên đưa cả hai web starter vào chỉ để bật GraphQL; hãy kiểm soát web application type và cấu hình runtime theo kiến trúc đã chọn.

## 4. POST request: cách gửi GraphQL operation phổ biến

POST là cách phổ biến để gửi GraphQL operation qua HTTP. Request body thường là JSON object với các thuộc tính:

| Thuộc tính | Bắt buộc? | Ý nghĩa |
|---|---|---|
| `query` | Có | GraphQL document chứa operation |
| `operationName` | Tùy trường hợp | Chọn operation cần thực thi khi document có nhiều operation |
| `variables` | Không | Map tên biến sang giá trị |
| `extensions` | Không | Metadata mở rộng, ví dụ persisted query protocol |

Ví dụ POST bằng curl:

~~~bash
curl -X POST http://localhost:8080/graphql \
  -H "Content-Type: application/json" \
  -H "Accept: application/graphql-response+json, application/json" \
  -d '{
    "query": "query BookById($id: ID!) { book(id: $id) { id title } }",
    "operationName": "BookById",
    "variables": {
      "id": "b-01"
    }
  }'
~~~

Trong ví dụ:

- `Content-Type: application/json` cho biết body là JSON.
- `Accept` nêu các response media type mà client có thể xử lý.
- `query` chứa operation.
- `operationName` xác định operation tên BookById.
- `variables` truyền ID tách khỏi GraphQL document.

Dùng variables giúp tái sử dụng cùng một document với nhiều giá trị khác nhau, giảm việc nối chuỗi query ở client và làm rõ kiểu dữ liệu đầu vào.

### Ví dụ response

Nếu sách tồn tại, server có thể trả:

~~~json
{
  "data": {
    "book": {
      "id": "b-01",
      "title": "GraphQL in Practice"
    }
  }
}
~~~

Nếu một field phát sinh lỗi trong quá trình thực thi, response GraphQL có thể chứa cả `data` và `errors`:

~~~json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Book was not found",
      "path": ["book"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

Client cần đọc cả phần data và errors. Không nên giả định mọi lỗi nghiệp vụ đều khiến HTTP request không nhận được JSON response.

## 5. operationName khi document có nhiều operation

Một GraphQL document có thể khai báo nhiều operation:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    id
    title
  }
}

query LatestBooks {
  latestBooks {
    id
    title
  }
}
~~~

Khi gửi document có nhiều operation, client phải chỉ định operation cần chạy bằng `operationName`:

~~~json
{
  "query": "query BookById($id: ID!) { book(id: $id) { id title } } query LatestBooks { latestBooks { id title } }",
  "operationName": "LatestBooks"
}
~~~

Nếu document chỉ có một operation, `operationName` có thể bỏ qua. Nếu có nhiều operation mà không xác định operation cần thực thi, GraphQL không thể chọn một cách an toàn và request sẽ thất bại ở bước validation/execution chuẩn bị.

Nên đặt tên operation có ý nghĩa để log, trace và phân tích hiệu năng dễ hơn. Tránh dùng cùng một tên chung như `Query1` cho mọi request.

## 6. GET request và giới hạn của GET

Một số GraphQL server hỗ trợ gửi Query bằng HTTP GET. Các tham số được đặt trong URL:

- `query`: GraphQL document đã URL-encode.
- `operationName`: tên operation nếu cần.
- `variables`: JSON được encode thành chuỗi.
- `extensions`: JSON metadata nếu được hỗ trợ.

Ví dụ về hình dạng request:

~~~http
GET /graphql?query=query%20BookById%28%24id%3AID%21%29%7Bbook%28id%3A%24id%29%7Bid%20title%7D%7D&operationName=BookById&variables=%7B%22id%22%3A%22b-01%22%7D
~~~

GET phù hợp với Query vì Query được thiết kế để đọc dữ liệu. Mutation làm thay đổi trạng thái server và không được thực thi bằng GET theo GraphQL-over-HTTP semantics. Một server tuân thủ giao thức phải từ chối mutation gửi qua GET, thường bằng HTTP 405.

Một số lưu ý khi dùng GET:

- URL có giới hạn độ dài tùy browser, proxy và server.
- Variables xuất hiện trong URL và có thể được ghi vào access log, browser history hoặc monitoring.
- GET có thể được cache bởi browser, proxy hoặc CDN nếu chính sách cache cho phép.
- Không đưa token, mật khẩu hoặc dữ liệu nhạy cảm vào query string.
- Không dùng GET cho mutation.

Trong thực tế, POST thường đơn giản và an toàn hơn cho operation có variables lớn hoặc dữ liệu nhạy cảm. Chỉ bật GET khi client, cache strategy và server đều có nhu cầu rõ ràng.

## 7. Content-Type và Accept

HTTP GraphQL có hai header quan trọng:

- `Content-Type` mô tả định dạng body mà client gửi.
- `Accept` mô tả định dạng response mà client muốn nhận.

Ví dụ request POST:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/graphql-response+json, application/json
~~~

`application/json` là media type request body phổ biến cho JSON GraphQL request. Với response, GraphQL-over-HTTP specification định nghĩa `application/graphql-response+json` là media type dành riêng cho GraphQL response; `application/json` vẫn được nhiều client/server hỗ trợ vì tương thích.

Client nên gửi Accept thể hiện rõ các media type mà nó hỗ trợ. Nếu server không hỗ trợ media type được yêu cầu, HTTP có thể trả lỗi content negotiation như 406. Nếu request dùng media type body không được hỗ trợ, server có thể từ chối bằng 415.

Đừng nhầm hai header:

| Header | Câu hỏi được trả lời |
|---|---|
| `Content-Type` | Body tôi đang gửi có định dạng gì? |
| `Accept` | Tôi có thể nhận response định dạng nào? |

## 8. Phân biệt HTTP error và GraphQL execution error

HTTP transport và GraphQL execution là hai tầng lỗi khác nhau.

### HTTP/transport error

Các lỗi xảy ra trước hoặc ngoài quá trình thực thi GraphQL, ví dụ:

- HTTP method không được hỗ trợ.
- Request body không phải JSON hợp lệ.
- Content-Type không được hỗ trợ.
- Request body vượt giới hạn server.
- Endpoint không tồn tại.
- Không đạt điều kiện xác thực ở web security layer.

Những lỗi này thường được biểu diễn bằng HTTP status code và có thể không có GraphQL response envelope.

### GraphQL request/execution error

Các lỗi xảy ra trong quá trình xử lý GraphQL, ví dụ:

- Query không hợp lệ theo schema.
- Variable không đúng kiểu.
- Resolver ném exception.
- Người dùng không được phép đọc một field.
- Custom scalar không serialize được giá trị.

GraphQL response có thể chứa `errors`, và trong lỗi khi thực thi field, có thể có cả `data` một phần.

Không nên chỉ kiểm tra HTTP status để xác định operation có thành công hay không. Client cần kiểm tra GraphQL response, đặc biệt là `errors`, `path` và `extensions`.

HTTP status và media type cụ thể còn phụ thuộc cách server triển khai GraphQL-over-HTTP và phiên bản Spring for GraphQL. Hãy kiểm thử hành vi thực tế của endpoint và thống nhất contract với client.

## 9. Spring MVC và Spring WebFlux

Spring for GraphQL hỗ trợ cả Spring MVC và Spring WebFlux. Cả hai đều có thể cung cấp HTTP endpoint cho GraphQL, nhưng mô hình xử lý request của web stack khác nhau.

| Tiêu chí | Spring MVC | Spring WebFlux |
|---|---|---|
| Nền tảng | Servlet API | Reactive Streams |
| Mô hình web | Blocking request thread | Non-blocking event loop khi dùng API reactive |
| Controller GraphQL | Annotated controller | Annotated controller |
| Reactive return type | Được Spring for GraphQL hỗ trợ | Tích hợp tự nhiên với reactive stack |
| Tích hợp blocking persistence | Phù hợp với JDBC/JPA truyền thống | Cần cô lập blocking call hoặc dùng reactive client |

Chọn MVC nếu phần lớn ứng dụng dùng Spring MVC và persistence đồng bộ như JPA/JDBC. Chọn WebFlux nếu ứng dụng đã theo reactive stack và các dependency downstream cũng hỗ trợ non-blocking.

Chỉ đổi sang WebFlux không tự động làm truy vấn database trở thành non-blocking. Nếu resolver gọi JPA trực tiếp trên event-loop thread, ứng dụng vẫn có nguy cơ nghẽn. Cần dùng reactive repository phù hợp hoặc cô lập blocking call theo đúng cách của Reactor.

## 10. WebGraphQlInterceptor: can thiệp vào request và response

`WebGraphQlInterceptor` là extension point ở tầng Spring GraphQL web request. Nó có thể:

- Đọc HTTP headers và metadata của request.
- Bổ sung thông tin vào GraphQL execution input/context.
- Ghi log hoặc trace request.
- Áp dụng chính sách chung trước khi operation chạy.
- Quan sát hoặc biến đổi response trước khi trả về transport.

Ví dụ thêm correlation ID vào GraphQLContext:

~~~java
@Component
public class RequestMetadataInterceptor
        implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String requestId =
                request.getHeaders().getFirst("X-Request-Id");

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context -> {
                    if (requestId != null) {
                        context.put("requestId", requestId);
                    }
                }).build());

        return chain.next(request);
    }
}
~~~

Resolver có thể đọc metadata:

~~~java
@QueryMapping
public Book book(DataFetchingEnvironment environment) {
    String requestId = environment.getGraphQlContext()
            .get("requestId");

    log.debug("Resolving book, requestId={}", requestId);

    String id = environment.getArgument("id");
    return bookService.findById(id);
}
~~~

Correlation ID hữu ích để nối log của HTTP request, resolver và service call. Nếu client gửi request ID, nên xác thực định dạng và giới hạn độ dài trước khi ghi log để tránh log injection hoặc log phình to.

Không dùng header do client tùy ý gửi làm bằng chứng danh tính hoặc quyền truy cập. Principal và tenant phải được xác định bởi Spring Security hoặc một cơ chế xác thực đáng tin cậy, sau đó mới được đưa vào GraphQLContext.

## 11. WebGraphQlInterceptor và Spring Security

HTTP request tới GraphQL endpoint đi qua web security chain như các endpoint khác. Có thể dùng Spring Security để xác thực request và áp dụng chính sách truy cập.

Một số lớp bảo vệ có thể phối hợp:

- HTTP security filter chain: xác thực request, kiểm tra CSRF, CORS và quyền truy cập endpoint.
- GraphQL interceptor: đưa metadata của principal đã xác thực vào GraphQLContext.
- Method/field security: bảo vệ resolver hoặc service theo quyền nghiệp vụ.
- Service/domain layer: kiểm tra quyền sở hữu tài nguyên và tenant.

Ví dụ, một resolver có thể lấy principal đã được xác thực từ context do ứng dụng thiết lập. Không nên tin một argument như `userId` hoặc header `X-User-Id` do client tự truyền để quyết định người dùng hiện tại.

GraphQL thường có một endpoint chung cho nhiều field, nên chỉ bảo vệ URL `/graphql` là chưa đủ. Một user có quyền gọi endpoint vẫn có thể không được phép đọc một field hoặc thực hiện một mutation cụ thể. Cần áp dụng authorization theo operation, field và tài nguyên.

Nếu dùng cookie/session authentication, cần cấu hình CSRF phù hợp vì POST GraphQL có thể thực hiện mutation. CORS chỉ kiểm soát browser origin được phép truy cập; nó không thay thế authentication hoặc authorization.

## 12. CORS cho HTTP GraphQL

Nếu frontend chạy ở origin khác backend, browser có thể gửi preflight request trước khi gửi GraphQL POST. Server cần cấu hình CORS cho endpoint GraphQL.

Các yếu tố cần xem xét:

- Allowed origins: chỉ các domain frontend được phép.
- Allowed methods: thường gồm POST và có thể GET nếu server hỗ trợ.
- Allowed headers: ví dụ `Authorization`, `Content-Type`, `Accept`, `X-Request-Id`.
- Allow credentials: chỉ bật khi thật sự dùng cookie hoặc credential cross-origin và cấu hình origin cụ thể.
- Exposed headers: chỉ khai báo header response mà browser client cần đọc.

Không nên dùng wildcard origin cùng credentials. Với môi trường production, khai báo origin cụ thể và kiểm tra cấu hình CORS ở đúng web stack đang chạy: Spring MVC hoặc Spring WebFlux.

CORS là chính sách của browser. Một client như curl hoặc backend service có thể gọi endpoint mà không chịu cùng cơ chế CORS của browser; do đó, CORS không phải ranh giới bảo mật API.

## 13. Giới hạn và bảo vệ HTTP endpoint

Một GraphQL request có thể chứa operation rất sâu hoặc yêu cầu số lượng field lớn. Vì endpoint thường dùng chung cho nhiều operation, server cần giới hạn tài nguyên ở nhiều tầng.

Các biện pháp thường dùng:

- Giới hạn kích thước HTTP request body.
- Cấu hình timeout cho request và lời gọi downstream.
- Giới hạn concurrency và số kết nối.
- Giới hạn pagination trong resolver/service.
- Dùng query depth hoặc complexity analysis nếu ứng dụng cần kiểm soát query tốn kém.
- Rate limit theo principal, API key hoặc IP phù hợp.
- Giới hạn số lượng alias/field theo chính sách ứng dụng.
- Bảo vệ mutation bằng authorization và validation.
- Không log toàn bộ variables nếu chúng có thể chứa dữ liệu nhạy cảm.

Ví dụ, resolver nên giới hạn kích thước trang:

~~~java
@QueryMapping
public List<Book> books(@Argument Integer first) {
    int limit = first == null ? 20 : first;

    if (limit < 1 || limit > 100) {
        throw new IllegalArgumentException(
                "first must be between 1 and 100");
    }

    return bookService.findFirst(limit);
}
~~~

Giới hạn ở controller chỉ là một lớp bảo vệ. Service và tầng truy vấn dữ liệu cũng nên bảo đảm không thể bị gọi với một giới hạn vượt quá chính sách từ một entry point khác.

## 14. HTTP caching và persisted query

GET có thể phù hợp với caching vì Query được thiết kế để đọc dữ liệu. Tuy nhiên, cache key cần phản ánh đầy đủ operation và variables. Với dữ liệu phụ thuộc người dùng, tenant hoặc quyền truy cập, cache công khai có thể làm lộ dữ liệu giữa các user.

POST thường không được cache theo mặc định như GET, dù có thể có caching tùy chỉnh ở hạ tầng.

Persisted query là kỹ thuật client gửi một định danh hoặc hash của query đã đăng ký thay vì gửi toàn bộ document trong mỗi request. Thông tin này thường được truyền qua `extensions`. Lợi ích có thể gồm:

- Giảm kích thước request.
- Cho phép server chỉ chấp nhận tập query đã duyệt.
- Hỗ trợ caching theo query identifier.
- Giảm việc client gửi document tùy ý nếu triển khai allowlist đúng cách.

Persisted query không tự động được bật chỉ vì request có trường `extensions`. Client và server cần thống nhất protocol, lưu trữ hash và chính sách fallback. Hãy xem đây là một tính năng triển khai riêng, không phải yêu cầu bắt buộc của HTTP GraphQL transport.

## 15. Kiểm thử HTTP endpoint bằng HttpGraphQlTester

`HttpGraphQlTester` cho phép kiểm thử GraphQL qua HTTP transport thay vì gọi trực tiếp GraphQL engine. Nó hữu ích để xác nhận endpoint path, request serialization, headers, response và interceptor.

Ví dụ tạo tester từ WebTestClient:

~~~java
WebTestClient webTestClient = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.builder(webTestClient).build();
~~~

Kiểm thử Query:

~~~java
@Test
void shouldExecuteBookQueryOverHttp() {
    graphQlTester.document("""
            query BookById($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
            .operationName("BookById")
            .variable("id", "b-01")
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("b-01");
}
~~~

Có thể thêm header cho request:

~~~java
HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.builder(webTestClient)
                .headers(headers ->
                        headers.setBearerAuth("test-token"))
                .build();
~~~

Token trong ví dụ là dữ liệu test; trong test thực tế, dùng token do security test fixture tạo ra.

Nên kiểm thử các tình huống:

1. POST request với query và variables hợp lệ.
2. Document có nhiều operation và operationName được chọn đúng.
3. GET Query nếu endpoint hỗ trợ GET.
4. Mutation gửi bằng GET bị từ chối.
5. Request body sai định dạng hoặc Content-Type không được hỗ trợ.
6. Authorization header và principal được nhận diện đúng.
7. Interceptor đưa correlation ID vào GraphQLContext.
8. CORS preflight từ origin được cho phép và origin bị từ chối.
9. GraphQL execution error có data/errors/path/extensions đúng.
10. Request quá lớn hoặc query vượt giới hạn bị từ chối theo chính sách.
11. Subscription được gửi qua transport streaming tương ứng thay vì HTTP request-response thông thường.

Nếu muốn kiểm tra chính xác HTTP status, headers hoặc media type, hãy dùng WebTestClient trực tiếp hoặc kết hợp với HttpGraphQlTester để xác minh cả tầng transport lẫn GraphQL payload.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Client nhận 404 | Gọi sai endpoint path | Kiểm tra `spring.graphql.path` |
| Client nhận 415 | Content-Type request không được hỗ trợ | Gửi media type JSON phù hợp |
| Client nhận 406 | Accept không có media type server hỗ trợ | Điều chỉnh Accept/content negotiation |
| Query chạy nhưng data null | Resolver, service hoặc GraphQL errors | Kiểm tra response `errors` và resolver |
| Mutation GET bị từ chối | GET không dùng để thực thi mutation | Gửi mutation bằng POST |
| Variables không bind | Sai tên biến, cấu trúc hoặc kiểu theo SDL | Kiểm tra document và variables |
| CORS preflight thất bại | Origin, method hoặc header chưa được cho phép | Cấu hình CORS trên web stack |
| Principal không có trong GraphQLContext | Chưa tích hợp security/interceptor | Đưa principal đã xác thực vào context |
| Subscription không hoạt động qua HTTP | HTTP request-response không duy trì event stream | Dùng WebSocket hoặc RSocket |
| Request lớn làm server chậm | Thiếu giới hạn body, pagination hoặc complexity | Bổ sung giới hạn ở web và GraphQL layer |

## 17. Nguyên tắc thiết kế HTTP GraphQL transport

Khi triển khai endpoint HTTP cho Spring for GraphQL:

- Dùng một endpoint rõ ràng và cấu hình bằng `spring.graphql.path`.
- Dùng POST làm phương thức mặc định cho operation, đặc biệt là mutation.
- Chỉ hỗ trợ GET cho Query và tuân thủ giới hạn của GraphQL-over-HTTP.
- Truyền variables riêng thay vì nối giá trị vào query string.
- Đặt Content-Type và Accept đúng media type.
- Phân biệt HTTP transport error với GraphQL execution error.
- Chọn Spring MVC hoặc WebFlux phù hợp với stack hiện có.
- Dùng `WebGraphQlInterceptor` cho metadata và cross-cutting logic ở tầng GraphQL web.
- Tích hợp Spring Security và authorization ở mức field/tài nguyên.
- Cấu hình CORS theo origin cụ thể; không xem CORS là authentication.
- Giới hạn request size, timeout, pagination, query complexity và rate.
- Không log secrets hoặc toàn bộ variables nhạy cảm.
- Dùng `HttpGraphQlTester` để kiểm thử qua HTTP transport.
- Dùng WebSocket hoặc RSocket cho GraphQL Subscription.

## Kết luận

HTTP GraphQL transport là lớp kết nối client với GraphQL execution qua HTTP. Spring Boot có thể tự cấu hình endpoint, thường tại `/graphql`, và Spring for GraphQL cung cấp handler cùng interceptor để xử lý request, context và response.

POST là phương thức phù hợp cho Query và Mutation; GET có thể dùng cho Query khi được hỗ trợ và không được dùng để thực thi mutation. Hiểu request payload, operationName, variables, Content-Type, Accept và ranh giới giữa HTTP error với GraphQL error giúp client-server trao đổi ổn định. Khi triển khai production, cần kết hợp transport với security, CORS, giới hạn tài nguyên, observability và kiểm thử qua `HttpGraphQlTester`.

## Tài liệu tham khảo

- [Spring for GraphQL — HTTP Transport](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Web Interception](https://docs.spring.io/spring-graphql/reference/transports.html#server.web-interception)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL over HTTP Specification](https://graphql.github.io/graphql-over-http/draft/)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
