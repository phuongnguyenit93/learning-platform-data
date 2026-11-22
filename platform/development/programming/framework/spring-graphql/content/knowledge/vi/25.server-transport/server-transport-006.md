# GraphQL HTTP request trong Spring for GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Mô tả cấu trúc một GraphQL request được gửi qua HTTP.
- Phân biệt các thành phần `query`, `operationName`, `variables` và `extensions`.
- Gửi Query và Mutation bằng HTTP POST với JSON body.
- Hiểu cách dùng HTTP GET cho Query và các giới hạn về cache, URL.
- Thiết lập `Content-Type`, `Accept` và các header cần thiết.
- Kết nối HTTP endpoint mặc định của Spring for GraphQL.
- Hiểu cách variables được chuyển thành argument của resolver.
- Phân biệt HTTP status với GraphQL errors trong response.
- Áp dụng authentication, CORS và giới hạn kích thước request.
- Kiểm thử HTTP request bằng `HttpGraphQlTester`.

## 1. GraphQL HTTP request là gì?

GraphQL định nghĩa một ngôn ngữ truy vấn và một định dạng response. Khi triển khai API qua HTTP, client gửi GraphQL document cùng các dữ liệu cần thiết tới endpoint của server.

Một endpoint thường phục vụ nhiều operation khác nhau:

- Query để đọc dữ liệu.
- Mutation để thay đổi dữ liệu.
- Subscription thường dùng một transport hỗ trợ luồng dữ liệu như WebSocket, không phải một HTTP request/response thông thường.

Trong Spring for GraphQL, HTTP request được tiếp nhận bởi GraphQL HTTP handler, chuyển thành GraphQL request để thực thi schema và resolver, sau đó kết quả được chuyển thành HTTP response.

Ví dụ client lấy thông tin sách:

~~~graphql
query FindBook {
    book(id: "book-42") {
        id
        title
    }
}
~~~

GraphQL document trên không phải toàn bộ HTTP request. Khi gửi qua HTTP, document được đặt trong một JSON object cùng những metadata cần thiết như operation name và variables.

## 2. Cấu trúc GraphQL request qua HTTP

Với JSON request thông thường, body có các trường sau:

| Trường | Bắt buộc? | Ý nghĩa |
| --- | --- | --- |
| `query` | Có trong request thông thường | GraphQL document chứa operation |
| `operationName` | Không, nếu document chỉ có một operation | Tên operation cần thực thi khi document có nhiều operation |
| `variables` | Không | JSON object chứa giá trị cho các variable trong document |
| `extensions` | Không | Metadata mở rộng theo thỏa thuận giữa client và server |

Ví dụ một POST body:

~~~json
{
    "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
    "operationName": "FindBook",
    "variables": {
        "id": "book-42"
    }
}
~~~

Server dùng `query` để parse và validate GraphQL document. `operationName` chọn operation cần thực thi. `variables` cung cấp giá trị runtime cho các biến đã khai báo trong document.

`extensions` dành cho metadata mở rộng như persisted query protocol nếu ứng dụng có triển khai. Không tự đặt các trường tùy ý trong `extensions` rồi giả định Spring for GraphQL hoặc mọi GraphQL server đều hiểu chúng.

Một request thường chỉ cần `query` nếu document có một operation và không sử dụng variables. Tuy nhiên, với ứng dụng thực tế, nên đặt tên operation và truyền dữ liệu động bằng variables.

## 3. Gửi request bằng HTTP POST

HTTP POST là cách phổ biến để gửi GraphQL Query và Mutation. Body chứa JSON với `Content-Type: application/json`.

Có thể dùng file request trong IntelliJ HTTP Client:

~~~http
POST http://localhost:8080/graphql
Content-Type: application/json
Accept: application/json

{
  "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
  "operationName": "FindBook",
  "variables": {
    "id": "book-42"
  }
}
~~~

Hoặc gửi Mutation:

~~~http
POST http://localhost:8080/graphql
Content-Type: application/json
Accept: application/json

{
  "query": "mutation RenameBook($id: ID!, $title: String!) { renameBook(id: $id, title: $title) { id title } }",
  "operationName": "RenameBook",
  "variables": {
    "id": "book-42",
    "title": "Spring for GraphQL"
  }
}
~~~

POST phù hợp khi document dài, variables lớn hoặc operation chứa dữ liệu không nên xuất hiện trên URL. POST cũng là lựa chọn rõ ràng cho Mutation.

Không gửi password, token hoặc dữ liệu nhạy cảm dưới dạng inline literal trong query document. Dùng variables để tách document khỏi dữ liệu runtime, đồng thời bảo đảm transport và log được cấu hình an toàn.

## 4. Tách GraphQL document và variables

Variables cho phép tái sử dụng cùng một document với nhiều bộ dữ liệu khác nhau.

GraphQL document:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

HTTP JSON body:

~~~json
{
    "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
    "operationName": "FindBook",
    "variables": {
        "id": "book-42"
    }
}
~~~

Trong document, `$id` là variable có kiểu `ID!`. Trong JSON, `variables.id` cung cấp giá trị `"book-42"`.

Với input object:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
    }
}
~~~

Body:

~~~json
{
    "query": "mutation CreateBook($input: CreateBookInput!) { createBook(input: $input) { id title } }",
    "operationName": "CreateBook",
    "variables": {
        "input": {
            "title": "Spring GraphQL",
            "isbn": "9780000000000"
        }
    }
}
~~~

JSON object trong `variables` phải phù hợp với kiểu input đã khai báo trong schema. GraphQL thực hiện coercion và validation trước khi gọi resolver. Nếu thiếu field bắt buộc hoặc truyền sai kiểu, operation có thể bị từ chối trước khi business resolver chạy.

## 5. operationName khi document có nhiều operation

Một document có thể khai báo nhiều operation:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}

query FindBooks {
    books {
        id
        title
    }
}
~~~

Khi gửi document này, client phải chỉ rõ operation muốn chạy bằng `operationName`:

~~~json
{
    "query": "query FindBook($id: ID!) { book(id: $id) { id title } } query FindBooks { books { id title } }",
    "operationName": "FindBooks",
    "variables": {}
}
~~~

Nếu document chỉ có một operation, `operationName` có thể được bỏ qua. Nếu document có nhiều operation mà không chỉ định operation name, server không thể xác định operation cần thực thi và sẽ trả lỗi GraphQL.

Tên operation phân biệt chữ hoa/chữ thường và phải khớp tên khai báo trong document. Không nhầm `operationName` với tên field hoặc tên method trong controller.

Đặt tên operation có ý nghĩa như `FindBook`, `SearchBooks`, `CreateBook` giúp log, tracing và theo dõi hiệu năng dễ dàng hơn.

## 6. HTTP GET cho GraphQL Query

GraphQL over HTTP cho phép gửi Query bằng HTTP GET nếu server hỗ trợ. Các tham số request được truyền qua query string, ví dụ:

~~~http
GET /graphql?query=query%20FindBook%28%24id%3A%20ID%21%29%7Bbook%28id%3A%24id%29%7Bid%20title%7D%7D&operationName=FindBook&variables=%7B%22id%22%3A%22book-42%22%7D
Accept: application/json
~~~

Các giá trị `query`, `operationName`, `variables` và `extensions` được URL encode. `variables` và `extensions` là JSON được encode thành chuỗi query parameter.

GET chỉ phù hợp với Query có tính chất đọc. Không gửi Mutation qua GET vì các intermediary, browser hoặc cache có thể xem GET là thao tác an toàn và có thể cache hoặc prefetch request. Subscription cần transport hỗ trợ stream.

Có một số giới hạn thực tế:

- URL có giới hạn độ dài tùy browser, proxy và web server.
- Query string có thể xuất hiện trong access log, browser history và hệ thống giám sát.
- Variables nhạy cảm trong URL dễ bị lưu lại ngoài ý muốn.
- Caching GET cần cache key và chính sách invalidation phù hợp.

Dù server có hỗ trợ GET, POST vẫn thường phù hợp hơn cho request có variables phức tạp hoặc dữ liệu nhạy cảm. Không coi việc dùng POST là thay thế cho authentication, authorization hay mã hóa TLS.

## 7. Content-Type và Accept

Hai header này có vai trò khác nhau:

| Header | Ý nghĩa |
| --- | --- |
| `Content-Type` | Mô tả định dạng body mà client gửi |
| `Accept` | Cho biết client chấp nhận định dạng response nào |

Với JSON POST request:

~~~http
Content-Type: application/json
Accept: application/json
~~~

`Content-Type: application/json` cho biết body là JSON chứa GraphQL request. `Accept: application/json` yêu cầu response ở định dạng JSON.

Nếu gửi body không đúng content type hoặc JSON không hợp lệ, request có thể bị từ chối ở tầng HTTP trước khi GraphQL operation được thực thi.

GraphQL over HTTP đang phát triển thêm quy ước media type response chuyên biệt. Khả năng hỗ trợ và content negotiation cụ thể phụ thuộc phiên bản Spring for GraphQL, Spring Boot và cấu hình transport. Khi tích hợp client, hãy dùng media type mà server đang hỗ trợ và kiểm tra hành vi với phiên bản thư viện của dự án.

## 8. HTTP endpoint mặc định trong Spring Boot

Spring Boot tự cấu hình HTTP GraphQL endpoint khi ứng dụng có starter phù hợp và schema được cung cấp. Đường dẫn mặc định thường là `/graphql`.

Có thể cấu hình lại path:

~~~yaml
spring:
  graphql:
    path: /api/graphql
~~~

Sau cấu hình, client gửi request tới:

~~~http
POST http://localhost:8080/api/graphql
Content-Type: application/json
Accept: application/json
~~~

Trong Spring for GraphQL, HTTP handler chuyển request thành `WebGraphQlRequest`, rồi chuyển tiếp qua web GraphQL chain để thực thi operation. Sau khi có `WebGraphQlResponse`, transport chuyển kết quả thành HTTP response.

Có thể hình dung:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Servlet hoặc WebFlux server"]
    B --> C["GraphQL HTTP handler"]
    C --> D["WebGraphQlRequest"]
    D --> E["WebGraphQlInterceptor chain"]
    E --> F["GraphQL execution"]
    F --> G["DataFetcher / Controller resolver"]
    G --> H["WebGraphQlResponse"]
    H --> I["HTTP JSON response"]
~~~

Endpoint HTTP phục vụ Query và Mutation theo mô hình request/response. Nếu ứng dụng có Subscription, cần cấu hình transport streaming phù hợp, thường là WebSocket.

Không nhầm `spring.graphql.path` với path của WebSocket endpoint hoặc path của các route REST khác trong ứng dụng.

## 9. Variables đi tới resolver như thế nào?

Sau khi GraphQL parse và validate document, các variables được áp dụng vào operation. Resolver nhận argument theo tên field trong schema.

SDL:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Controller:

~~~java
@Controller
class BookQueryController {

    private final BookService bookService;

    BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") UUID id) {
        return bookService.findById(id);
    }
}
~~~

HTTP body:

~~~json
{
    "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
    "operationName": "FindBook",
    "variables": {
        "id": "book-42"
    }
}
~~~

GraphQL lấy giá trị variable `$id`, gán cho argument `id` của field `book`, sau đó Spring for GraphQL bind argument vào tham số `@Argument("id")`.

Việc chuyển từ GraphQL scalar `ID` sang Java `UUID` phụ thuộc scalar configuration và cơ chế conversion của ứng dụng. Nếu schema sử dụng custom scalar, hãy đăng ký scalar coercing và kiểm thử dữ liệu đầu vào tương ứng.

Với input object, có thể bind thành DTO hoặc Java record:

~~~java
public record CreateBookInput(
        String title,
        String isbn) {
}

@MutationMapping
public Book createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
~~~

HTTP request không cần biết Java class. Client chỉ gửi JSON đúng theo GraphQL input type; Spring xử lý binding ở server.

## 10. HTTP response và GraphQL response

HTTP response thường có JSON body chứa `data`, `errors` hoặc cả hai.

Response thành công:

~~~json
{
    "data": {
        "book": {
            "id": "book-42",
            "title": "Spring GraphQL"
        }
    }
}
~~~

Response có field error:

~~~json
{
    "data": {
        "book": {
            "id": "book-42",
            "title": null
        }
    },
    "errors": [
        {
            "message": "Không thể tải tiêu đề sách.",
            "path": [
                "book",
                "title"
            ],
            "extensions": {
                "code": "BOOK_TITLE_UNAVAILABLE"
            }
        }
    ]
}
~~~

GraphQL có thể trả partial data khi một field lỗi nhưng các field khác vẫn thành công. Client cần kiểm tra `errors` thay vì chỉ kiểm tra `data` có tồn tại hay không.

Không phải mọi GraphQL error đều tương đương HTTP 4xx hoặc 5xx. Lỗi parse, validation và field execution được biểu diễn theo GraphQL response; HTTP status cụ thể còn phụ thuộc media type, transport và cấu hình server. Vì vậy, client nên đọc cả HTTP status lẫn GraphQL response body.

## 11. Authentication và HTTP headers

Authentication thường được truyền qua HTTP header, chẳng hạn Bearer token:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/json
Authorization: Bearer <access-token>
~~~

Spring Security có thể xác thực request ở web security filter chain trước khi GraphQL handler thực thi. Principal đã xác thực có thể được dùng trong resolver hoặc đưa vào GraphQL context theo cấu hình ứng dụng.

Một số nguyên tắc:

- Không truyền access token qua GraphQL variables.
- Không đặt token trong query string.
- Không log `Authorization`, `Cookie` hoặc token.
- Kiểm tra quyền ở server, không tin argument do client gửi.
- Xác định rõ security policy cho từng field hoặc operation.
- Dùng HTTPS trong môi trường có dữ liệu xác thực hoặc dữ liệu riêng tư.

GraphQL request body và HTTP headers có vai trò khác nhau: body mô tả operation và input; headers mang metadata transport và thông tin xác thực. Giữ ranh giới này giúp API dễ bảo trì và giảm nguy cơ lộ thông tin.

## 12. CORS và browser request

Khi frontend chạy ở origin khác backend, browser áp dụng Cross-Origin Resource Sharing (CORS). CORS là cơ chế của browser và HTTP, không phải một phần của GraphQL schema.

Một JSON POST có thể kích hoạt preflight `OPTIONS`, đặc biệt khi request dùng `Content-Type: application/json` hoặc header `Authorization`.

Server cần cho phép đúng origin, method và header mà frontend sử dụng. Ví dụ cấu hình khái niệm:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class GraphQlCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of("https://app.example.com"));
        configuration.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        configuration.setAllowedHeaders(
                List.of("Content-Type", "Authorization")
        );

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/graphql", configuration);
        return source;
    }
}
~~~

Ví dụ này cần được tích hợp với cấu hình Spring Security của ứng dụng. Không dùng wildcard origin cho API có credentials nếu chính sách bảo mật không cho phép. Chỉ mở các origin, method và header thực sự cần thiết.

CORS không thay thế authentication hay authorization. Một client ngoài browser vẫn có thể gọi endpoint trực tiếp; server phải tự xác minh danh tính và quyền truy cập.

## 13. Giới hạn request và bảo vệ server

GraphQL cho phép client chọn nhiều field và nested relation trong một operation. Vì vậy, một HTTP request nhỏ vẫn có thể tạo ra lượng công việc lớn ở server.

Nên áp dụng các giới hạn phù hợp:

- Giới hạn kích thước HTTP request body.
- Giới hạn số lượng variables và kích thước input object.
- Giới hạn độ sâu query hoặc độ phức tạp operation nếu hệ thống hỗ trợ.
- Giới hạn số phần tử list và pagination size.
- Đặt timeout cho database và downstream service.
- Giới hạn request rate và số request đồng thời.
- Kiểm soát persisted query hoặc allowlist nếu API cần giới hạn document được phép chạy.

Không chỉ dựa vào giới hạn kích thước body. Một query document ngắn vẫn có thể tạo nhiều nested resolver hoặc truy vấn dữ liệu lớn. Cần kết hợp giới hạn transport với kiểm soát ở tầng GraphQL và service.

## 14. Extensions và persisted query

`extensions` là trường tùy chọn trong GraphQL HTTP request dành cho metadata mở rộng. Một số hệ thống dùng nó cho persisted query, tracing metadata hoặc protocol extension đã thống nhất.

Ví dụ cấu trúc khái niệm của persisted query extension:

~~~json
{
    "query": "",
    "operationName": "FindBook",
    "variables": {
        "id": "book-42"
    },
    "extensions": {
        "persistedQuery": {
            "version": 1,
            "sha256Hash": "<query-hash>"
        }
    }
}
~~~

Đây chỉ là ví dụ về hình dạng của một extension protocol. Server phải triển khai và bật đúng cơ chế persisted query tương ứng thì mới hiểu extension đó. Spring for GraphQL không tự động hỗ trợ mọi extension chỉ vì request có trường `extensions`.

Persisted query có thể giảm lượng query document phải gửi và hỗ trợ allowlist operation. Tuy nhiên, cần quản lý hash, version, cache và quy trình cập nhật document. Không coi một hash do client gửi là bằng chứng authorization; server vẫn phải xác thực và kiểm tra quyền.

## 15. Kiểm thử HTTP request bằng HttpGraphQlTester

`HttpGraphQlTester` gửi operation qua HTTP transport thật hoặc test web client, giúp kiểm tra cả request binding lẫn response.

Ví dụ tạo tester bằng `WebTestClient`:

~~~java
WebTestClient webTestClient = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.create(webTestClient);
~~~

Gửi Query với variable:

~~~java
graphQlTester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "book-42")
        .execute()
        .path("book.id")
        .entity(String.class)
        .isEqualTo("book-42");
~~~

Kiểm thử Mutation với input object:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
            }
        }
        """)
        .variable("input", Map.of(
                "title", "Spring GraphQL",
                "isbn", "9780000000000"
        ))
        .execute()
        .path("createBook.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

Các tình huống nên kiểm thử:

- POST request với JSON body hợp lệ.
- Document có nhiều operation và operationName được chọn đúng.
- Variables bind đúng vào `@Argument` và input DTO.
- Thiếu variable bắt buộc hoặc sai kiểu trả GraphQL error.
- Authentication header được áp dụng đúng.
- Request không có quyền bị từ chối theo security policy.
- CORS preflight được cấu hình phù hợp nếu có browser client.
- Request body vượt giới hạn bị từ chối.
- Response có partial data và errors được client xử lý đúng.

Dùng `HttpGraphQlTester` khi muốn kiểm thử HTTP transport. Nếu chỉ kiểm thử GraphQL execution mà không cần HTTP, có thể dùng `ExecutionGraphQlServiceTester`; hai loại tester phục vụ phạm vi khác nhau.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Server báo thiếu query | Body không có trường `query` hoặc JSON sai cấu trúc | Kiểm tra JSON request |
| Chạy nhầm operation | Document có nhiều operation nhưng operationName sai hoặc thiếu | Chỉ định operationName chính xác |
| Resolver nhận argument null | Tên variable, argument hoặc key trong variables không khớp | Đối chiếu SDL, document và JSON variables |
| Input object không bind được | JSON không đúng cấu trúc GraphQL input type | Kiểm tra schema và kiểu field |
| HTTP 415 Unsupported Media Type | Content-Type không được server hỗ trợ | Gửi `application/json` cho JSON body |
| Browser bị CORS error | Origin, method hoặc header chưa được cho phép | Cấu hình CORS tại web/security layer |
| Query GET bị URL quá dài | Document hoặc variables lớn | Dùng POST |
| Client chỉ kiểm tra HTTP 200 rồi bỏ qua lỗi | GraphQL errors nằm trong response body | Đọc cả `data` và `errors` |
| Token xuất hiện trong log | Ghi toàn bộ headers hoặc query string | Redact Authorization và tránh token trên URL |
| Request đơn giản làm server quá tải | Query có depth/complexity hoặc list size lớn | Giới hạn operation và pagination |
| `extensions` bị bỏ qua | Server chưa triển khai protocol extension tương ứng | Cấu hình đúng extension hoặc không gửi trường đó |

## 17. Quy trình gửi GraphQL HTTP request

Khi tích hợp client với Spring for GraphQL, hãy thực hiện theo trình tự:

1. **Xác định operation.** Chọn Query hoặc Mutation; dùng transport subscription riêng cho Subscription.
2. **Viết GraphQL document.** Khai báo field, arguments và variables.
3. **Đặt operation name.** Đặc biệt khi document có nhiều operation.
4. **Chuẩn bị variables.** Gửi JSON object khớp với scalar và input type trong schema.
5. **Chọn HTTP method.** Dùng POST cho phần lớn request; chỉ dùng GET cho Query khi server hỗ trợ và dữ liệu phù hợp với URL.
6. **Thiết lập headers.** Gửi Content-Type, Accept và Authorization khi cần.
7. **Gửi tới endpoint.** Dùng path Spring GraphQL đang cấu hình, mặc định thường là `/graphql`.
8. **Đọc response.** Kiểm tra cả `data`, `errors`, HTTP status và response headers.
9. **Bảo vệ request.** Không đặt token hoặc dữ liệu nhạy cảm trong URL, query document hay log.
10. **Kiểm thử và giới hạn tải.** Dùng `HttpGraphQlTester`, kiểm tra validation, authorization, CORS và request size.

## 18. Tổng kết

GraphQL HTTP request là cách client gửi GraphQL document tới server qua HTTP. Với JSON request, các trường quan trọng là `query`, `operationName`, `variables` và `extensions`. HTTP POST là lựa chọn phổ biến cho Query và Mutation; GET có thể dùng cho Query khi server hỗ trợ, nhưng cần chú ý giới hạn URL, caching và dữ liệu nhạy cảm.

Trong Spring for GraphQL, Spring Boot thường cung cấp endpoint `/graphql` và chuyển HTTP request thành GraphQL execution. Variables được validate theo schema rồi bind vào `@Argument` hoặc input DTO của resolver. HTTP response có thể chứa `data`, `errors` hoặc cả hai, nên client phải kiểm tra GraphQL errors thay vì chỉ dựa vào HTTP status. Kết hợp headers đúng, authentication, CORS, giới hạn request và `HttpGraphQlTester` giúp xây dựng luồng HTTP GraphQL rõ ràng, an toàn và có thể kiểm thử.

