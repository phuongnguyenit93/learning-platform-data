# ExecutionGraphQlService trong Spring for GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của `ExecutionGraphQlService` trong kiến trúc Spring for GraphQL.
- Phân biệt `ExecutionGraphQlService`, `DefaultExecutionGraphQlService`, `GraphQlSource` và `WebGraphQlHandler`.
- Mô tả đường đi của một GraphQL request từ transport đến GraphQL Java engine và quay lại client.
- Hiểu dữ liệu mà `ExecutionGraphQlRequest` mang vào quá trình thực thi và response được tạo ra như thế nào.
- Biết cách Spring Boot cung cấp execution service mặc định và khi nào cần thay thế hoặc bọc service.
- Chọn đúng điểm mở rộng cho context, xử lý lỗi, logging, metrics và kiểm thử.
- Tránh đưa logic nghiệp vụ hoặc xử lý transport sai tầng vào execution service.

## 1. ExecutionGraphQlService là gì?

`ExecutionGraphQlService` là hợp đồng thực thi GraphQL request trong Spring for GraphQL. Nó nhận một request đã được biểu diễn dưới dạng đối tượng của Spring GraphQL, chuyển yêu cầu đó vào GraphQL runtime và trả về kết quả thực thi theo mô hình reactive.

Có thể hình dung trách nhiệm của nó bằng một câu: **nhận thông tin operation, yêu cầu GraphQL engine thực thi operation đó và trả kết quả về cho tầng gọi nó**.

Hợp đồng có dạng:

~~~java
public interface ExecutionGraphQlService {

    Mono<ExecutionGraphQlResponse> execute(ExecutionGraphQlRequest request);
}
~~~

Các kiểu dữ liệu chính:

- `ExecutionGraphQlRequest` biểu diễn yêu cầu cần thực thi, bao gồm document GraphQL, operation name, variables và những thông tin ngữ cảnh liên quan.
- `ExecutionGraphQlResponse` biểu diễn kết quả thực thi, bao gồm dữ liệu, lỗi và các thông tin mở rộng mà GraphQL runtime tạo ra.
- `Mono` là kiểu trả về của Reactor, biểu diễn một kết quả bất đồng bộ có thể hoàn tất sau đó hoặc kết thúc bằng lỗi ở tầng reactive.

`ExecutionGraphQlService` là một thành phần phía server, không phải URL endpoint mà client gọi trực tiếp. Client gửi request qua HTTP, WebSocket hoặc transport được ứng dụng hỗ trợ. Thành phần xử lý transport chuyển request vào chuỗi xử lý web; chuỗi này mới gọi execution service.

Trong ứng dụng Spring Boot thông thường, bạn không cần tự viết implementation của interface này. Spring Boot có thể cấu hình implementation mặc định dựa trên `GraphQlSource` và các thành phần GraphQL đã được đăng ký.

## 2. Vị trí của execution service trong kiến trúc

Một ứng dụng Spring for GraphQL có nhiều lớp. Mỗi lớp xử lý một phần trách nhiệm:

| Thành phần | Trách nhiệm |
| --- | --- |
| HTTP, WebSocket hoặc RSocket handler | Nhận dữ liệu từ transport và ghi response về client |
| `WebGraphQlHandler` | Điều phối xử lý request ở tầng web GraphQL |
| `WebGraphQlInterceptor` | Can thiệp request/response web, bổ sung context hoặc metadata |
| `ExecutionGraphQlService` | Điều phối việc thực thi một GraphQL request |
| `GraphQlSource` | Cung cấp GraphQL runtime được xây dựng từ schema và runtime wiring |
| GraphQL Java engine | Parse, validate, chọn operation và thực thi các field |
| DataFetcher hoặc controller | Cung cấp giá trị cho field theo schema |

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["GraphQL client"] --> B["HTTP / WebSocket / RSocket"]
    B --> C["WebGraphQlHandler"]
    C --> D["WebGraphQlInterceptor chain"]
    D --> E["ExecutionGraphQlService"]
    E --> F["GraphQL engine from GraphQlSource"]
    F --> G["DataFetcher / @Controller"]
    G --> F
    F --> H["ExecutionGraphQlResponse"]
    H --> C
    C --> B
    B --> A
~~~

`GraphQlSource` và `ExecutionGraphQlService` có quan hệ gần nhau nhưng không thay thế nhau:

- `GraphQlSource` cung cấp cấu hình và GraphQL runtime, được xây dựng từ schema SDL, runtime wiring, scalar, instrumentation và các thành phần liên quan.
- `ExecutionGraphQlService` nhận từng request và yêu cầu runtime thực thi request đó.

Một cách so sánh dễ nhớ: `GraphQlSource` cung cấp bộ máy GraphQL đã được cấu hình; execution service đưa từng operation vào bộ máy đó.

`WebGraphQlHandler` đứng ở tầng cao hơn. Nó kết nối chuỗi interceptor với execution service và tạo response cho tầng transport. Vì vậy, khi cần đọc header HTTP, xác định thông tin người dùng hoặc bổ sung dữ liệu theo request, interceptor thường là điểm mở rộng phù hợp hơn.

## 3. Đường đi của một request

Giả sử client gửi operation:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Variables:

~~~json
{
    "id": "book-42"
}
~~~

Một request đi qua các bước khái quát sau.

1. **Transport nhận request.** HTTP handler hoặc WebSocket handler nhận nội dung từ client và chuyển nó thành request mà Spring for GraphQL có thể xử lý.
2. **Web handler tạo ngữ cảnh xử lý.** `WebGraphQlHandler` chạy chuỗi `WebGraphQlInterceptor`. Interceptor có thể bổ sung thông tin xác thực, tenant, correlation ID hoặc dữ liệu ngữ cảnh khác.
3. **Execution service nhận request.** `ExecutionGraphQlService.execute(...)` nhận `ExecutionGraphQlRequest` đã được chuẩn bị cho quá trình thực thi.
4. **GraphQL runtime xử lý operation.** GraphQL Java parse document, kiểm tra cú pháp và schema, chọn operation, kiểm tra variables, rồi thực thi selection set.
5. **Các field được resolve.** Runtime gọi DataFetcher tương ứng. Trong ứng dụng Spring, DataFetcher có thể được tạo từ controller method như `@QueryMapping`, `@SchemaMapping` hoặc các cơ chế wiring khác.
6. **Kết quả được đóng gói.** Execution service trả `ExecutionGraphQlResponse` cho web handler.
7. **Transport gửi response.** Web handler và transport chuyển kết quả thành response phù hợp với giao thức client đang dùng.

Execution service không tự quyết định dữ liệu nghiệp vụ của field `book`. Nó khởi chạy quá trình thực thi; DataFetcher hoặc controller chịu trách nhiệm cung cấp giá trị field.

### 3.1. Parse và validation diễn ra ở đâu?

Client gửi document dưới dạng văn bản GraphQL. GraphQL Java chịu trách nhiệm phân tích document, kiểm tra operation với schema và thực thi. Những lỗi như sai cú pháp, chọn field không tồn tại hoặc truyền argument sai kiểu được phát hiện trong quá trình xử lý của GraphQL engine.

Do đó, không nên hiểu execution service là một parser hoặc một nơi tự viết lại các quy tắc GraphQL. Service làm nhiệm vụ điều phối việc thực thi thông qua runtime đã được cấu hình.

### 3.2. Một request có thể chứa nhiều operation

Một document có thể khai báo nhiều operation:

~~~graphql
query GetBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}

query GetBooks {
    books {
        id
        title
    }
}
~~~

Khi document có nhiều operation, request cần chỉ rõ operation name để GraphQL runtime biết operation nào sẽ thực thi. Nếu document chỉ có một operation, operation name có thể được bỏ qua.

Execution service chuyển thông tin operation name cùng document và variables vào quá trình thực thi. Việc chọn operation và kiểm tra tính hợp lệ thuộc về GraphQL engine.

## 4. ExecutionGraphQlRequest và ExecutionGraphQlResponse

### 4.1. Request chứa những gì?

`ExecutionGraphQlRequest` là biểu diễn request ở tầng thực thi. Tùy cách request được tạo và transport sử dụng, các thông tin quan trọng thường gồm:

| Thông tin | Mục đích |
| --- | --- |
| Document | Nội dung GraphQL operation |
| Operation name | Chọn operation khi document có nhiều operation |
| Variables | Giá trị đầu vào cho các biến được khai báo trong operation |
| Extensions | Metadata mở rộng của request, ví dụ quy ước persisted query |
| GraphQL context | Dữ liệu ngữ cảnh dùng chung trong một lần thực thi |
| Locale | Ngôn ngữ/khu vực có thể được dùng trong xử lý hoặc phân giải thông báo |
| Execution ID | Định danh một lần thực thi, hữu ích khi theo dõi và đối chiếu log |

Không phải mọi transport đều cung cấp mọi metadata. Ví dụ, header HTTP chỉ có ở tầng web request; một execution request thuần túy không nên được xem như đối tượng chứa toàn bộ chi tiết của HTTP exchange.

Variables được kiểm tra theo kiểu đã khai báo trong schema. Nếu operation yêu cầu `ID!` mà client không cung cấp giá trị phù hợp, GraphQL runtime có thể trả lỗi trước khi resolver nghiệp vụ được gọi.

### 4.2. Response chứa dữ liệu và lỗi

Một response thành công thường có cấu trúc:

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

Nếu một field phát sinh lỗi trong lúc thực thi, response có thể chứa cả `data` và `errors`:

~~~json
{
    "data": {
        "book": null
    },
    "errors": [
        {
            "message": "Book not found",
            "path": ["book"]
        }
    ]
}
~~~

Đây là cấu trúc minh họa. Nội dung lỗi thực tế phụ thuộc vào GraphQL engine, DataFetcher và cơ chế xử lý lỗi của ứng dụng.

Cần phân biệt hai nhóm lỗi:

- **Lỗi parse/validation/coercion:** operation sai cú pháp, không phù hợp schema hoặc variables không hợp lệ. GraphQL engine không thể thực thi operation như yêu cầu.
- **Lỗi trong execution:** một DataFetcher hoặc thành phần được gọi trong lúc resolve field gặp lỗi. GraphQL có thể vẫn trả dữ liệu của những field khác, cùng danh sách lỗi.

`ExecutionGraphQlResponse` là kết quả ở tầng Spring GraphQL. Tầng transport tiếp tục chuyển kết quả này thành response phù hợp với HTTP hoặc giao thức đang dùng. Vì vậy, lỗi GraphQL không đồng nghĩa mọi trường hợp đều phải biến thành HTTP 500.

## 5. DefaultExecutionGraphQlService

`DefaultExecutionGraphQlService` là implementation tiêu chuẩn của `ExecutionGraphQlService`. Nó sử dụng `GraphQlSource` để lấy GraphQL runtime và thực thi request thông qua GraphQL Java.

Trong ứng dụng Spring Boot, auto-configuration thường tạo execution service mặc định khi các thành phần cần thiết đã có. Với cấu hình thông thường, bạn chỉ cần cung cấp schema, runtime wiring và các resolver; không cần tự tạo service.

Nếu tự lắp ráp Spring GraphQL ngoài auto-configuration, có thể tạo implementation mặc định từ `GraphQlSource`:

~~~java
@Bean
ExecutionGraphQlService executionGraphQlService(GraphQlSource graphQlSource) {
    return new DefaultExecutionGraphQlService(graphQlSource);
}
~~~

Đây là cấu hình minh họa cho trường hợp bạn chủ động quản lý bean. Nếu ứng dụng đã dùng auto-configuration và không có yêu cầu tùy chỉnh execution service, hãy để Spring Boot cung cấp implementation mặc định.

### 5.1. Vì sao nên giữ implementation mặc định?

Implementation mặc định kết nối các abstraction của Spring GraphQL với GraphQL Java. Nó giúp ứng dụng dùng chung cơ chế thực thi đã được tích hợp với:

- `GraphQlSource` và schema runtime.
- Request/response abstraction của Spring GraphQL.
- Mô hình reactive được dùng trong API thực thi.
- Các extension point chuyên biệt như interceptor, instrumentation và xử lý lỗi.

Tự viết implementation chỉ để gọi một resolver hoặc truy vấn repository sẽ làm sai ranh giới trách nhiệm. Resolver là nơi phù hợp để thực hiện logic nghiệp vụ; execution service nên giữ vai trò điều phối toàn bộ operation.

## 6. Bổ sung dữ liệu ngữ cảnh trước khi thực thi

Một yêu cầu thường gặp là đưa thông tin người dùng, tenant hoặc correlation ID vào quá trình resolve field. Nguồn dữ liệu này thường đến từ HTTP header, security context hoặc metadata của transport.

`WebGraphQlInterceptor` là điểm mở rộng phù hợp vì nó làm việc ở tầng web request trước khi gọi execution service.

Ví dụ bổ sung tenant vào GraphQL context:

~~~java
@Component
class TenantGraphQlInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        String tenantId = request.getHeaders().getFirst("X-Tenant-Id");

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context ->
                        context.put("tenantId", tenantId)));

        return chain.next(request);
    }
}
~~~

Trong ví dụ, interceptor đọc header của request và đặt tenant ID vào GraphQL context. Những DataFetcher trong cùng lần thực thi có thể truy cập dữ liệu này thông qua context.

Ví dụ resolver đọc giá trị context:

~~~java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Book book(
            @Argument String id,
            DataFetchingEnvironment environment) {

        String tenantId = environment.getGraphQlContext()
                .get("tenantId");

        return bookService.findById(tenantId, id);
    }
}
~~~

Ví dụ chỉ minh họa cách truyền ngữ cảnh. Trong ứng dụng thực tế, tenant ID phải được xác thực và ràng buộc với danh tính hoặc quyền truy cập đã được xác minh. Không nên tin một header do client tự gửi nếu header đó có thể cho phép người dùng truy cập dữ liệu của tenant khác.

Một số nguyên tắc khi dùng GraphQL context:

- Chỉ đặt dữ liệu cần dùng trong một lần thực thi.
- Dùng context để truyền metadata và thông tin ngữ cảnh, không biến nó thành nơi chứa toàn bộ trạng thái ứng dụng.
- Không đặt secret hoặc thông tin nhạy cảm vào log khi ghi lại context.
- Tạo dữ liệu theo request; tránh dùng một mutable map dùng chung giữa nhiều request.
- Dùng cơ chế xác thực và phân quyền của ứng dụng để xác minh danh tính trước khi đưa thông tin tin cậy vào context.

## 7. ExecutionGraphQlService và các điểm mở rộng khác

Không phải mọi yêu cầu tùy chỉnh đều cần thay thế execution service. Spring for GraphQL cung cấp extension point ở nhiều tầng.

| Nhu cầu | Điểm mở rộng phù hợp |
| --- | --- |
| Đọc HTTP header, bổ sung context, xử lý metadata web | `WebGraphQlInterceptor` |
| Thay đổi cách thực thi GraphQL ở cấp service | `ExecutionGraphQlService` |
| Xây dựng schema, runtime wiring, scalar và DataFetcher | `GraphQlSource` |
| Xử lý exception phát sinh từ DataFetcher | `DataFetcherExceptionResolver` hoặc `@GraphQlExceptionHandler` |
| Đo lường hoặc can thiệp vòng đời GraphQL engine | GraphQL Java `Instrumentation` |
| Thực thi nghiệp vụ cho một field | Controller method, `@SchemaMapping` hoặc DataFetcher |
| Tải theo lô và giảm N+1 | `BatchLoaderRegistry`, DataLoader và `@BatchMapping` |

### 7.1. Khi nào nên tùy chỉnh ExecutionGraphQlService?

Chỉ cân nhắc tùy chỉnh khi cần thay đổi hành vi điều phối thực thi ở cấp service và các extension point chuyên biệt khác không đáp ứng được yêu cầu. Một số ví dụ:

- Bọc service để đo thời gian thực thi ở ranh giới service.
- Tích hợp một cơ chế điều phối execution riêng của ứng dụng.
- Áp dụng một chính sách chung cần chạy trước hoặc sau mọi lần thực thi ở đúng tầng này.

Nếu mục tiêu chỉ là đọc header, thêm user vào context hoặc chuyển exception thành lỗi GraphQL, hãy ưu tiên interceptor hoặc exception resolver. Nếu mục tiêu là lấy dữ liệu của field, hãy triển khai DataFetcher hoặc controller.

### 7.2. Bọc service để ghi nhận thời gian

Một decorator có thể ủy quyền cho implementation khác và ghi nhận thời gian hoàn tất:

~~~java
final class MeasuredExecutionGraphQlService
        implements ExecutionGraphQlService {

    private final ExecutionGraphQlService delegate;
    private final GraphQlMetrics metrics;

    MeasuredExecutionGraphQlService(
            ExecutionGraphQlService delegate,
            GraphQlMetrics metrics) {
        this.delegate = delegate;
        this.metrics = metrics;
    }

    @Override
    public Mono<ExecutionGraphQlResponse> execute(
            ExecutionGraphQlRequest request) {

        long startedAt = System.nanoTime();

        return this.delegate.execute(request)
                .doOnNext(response -> this.metrics.record(
                        request.getOperationName(),
                        System.nanoTime() - startedAt));
    }
}
~~~

`GraphQlMetrics` trong ví dụ là thành phần do ứng dụng định nghĩa. Decorator giữ nguyên kết quả của delegate và chỉ quan sát thời điểm response được phát ra.

Khi triển khai thật, cần quyết định cách ghi nhận cả trường hợp lỗi hoặc hủy subscription reactive. Có thể dùng các operator như `doOnError` hoặc `doFinally` tùy mục tiêu đo lường. Không nên ghi toàn bộ document và variables một cách mặc định vì chúng có thể chứa dữ liệu nhạy cảm.

Khi đăng ký decorator trong Spring, phải bảo đảm có một delegate thực sự và chỉ có một execution service được chọn cho web handler. Tránh cấu hình bean tự inject chính nó hoặc tạo vòng phụ thuộc. Nếu cần bọc implementation mặc định, hãy tạo delegate từ `GraphQlSource` một cách tường minh rồi bọc delegate đó.

## 8. Mô hình reactive của execution service

API của `ExecutionGraphQlService` trả về `Mono<ExecutionGraphQlResponse>`. Điều này cho phép tầng gọi service phối hợp với xử lý bất đồng bộ trong Spring GraphQL.

Cần phân biệt:

- `Mono` biểu diễn kết quả của một lần gọi execution service.
- `Flux` biểu diễn một chuỗi phần tử trong Reactor.
- GraphQL Subscription biểu diễn một operation tạo ra luồng sự kiện theo mô hình GraphQL và transport hỗ trợ subscription.

Không nên kết luận rằng vì execution service trả `Mono` nên Subscription chỉ có thể phát một sự kiện. `Mono` ở đây là kết quả bất đồng bộ của lời gọi service; kết quả GraphQL của một subscription còn có ngữ nghĩa stream riêng và được các tầng Spring GraphQL/transport xử lý tương ứng.

### 8.1. Tránh chặn luồng xử lý

Khi viết code quanh execution service, không nên gọi các thao tác chặn như `block()` trong chuỗi reactive của request. Việc chặn có thể làm giảm khả năng xử lý đồng thời hoặc gây deadlock tùy môi trường thực thi.

Ví dụ không nên dùng trong request path:

~~~java
ExecutionGraphQlResponse response =
        delegate.execute(request).block();
~~~

Hãy giữ kết quả dưới dạng reactive và nối thêm xử lý bằng các operator phù hợp:

~~~java
return delegate.execute(request)
        .doOnNext(this::recordResponse);
~~~

Nếu một service nghiệp vụ bên dưới là blocking, cần đặt nó trên scheduler phù hợp hoặc dùng cách tích hợp blocking được Spring hỗ trợ. Không nên tự ý chuyển mọi đoạn xử lý sang scheduler khác mà không hiểu mô hình thực thi của ứng dụng.

## 9. Xử lý lỗi trong mối quan hệ với execution service

Execution service trả kết quả từ GraphQL runtime. Cách ứng dụng chuyển exception của DataFetcher thành lỗi GraphQL thường được xử lý ở extension point dành cho lỗi.

Ví dụ một exception nghiệp vụ:

~~~java
class BookNotFoundException extends RuntimeException {

    BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}
~~~

Resolver có thể ném exception khi không tìm thấy sách:

~~~java
@QueryMapping
Book book(@Argument String id) {
    return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

Ứng dụng có thể ánh xạ exception sang lỗi GraphQL bằng `DataFetcherExceptionResolver` hoặc cơ chế `@GraphQlExceptionHandler` của Spring for GraphQL. Ví dụ minh họa với controller advice:

~~~java
@ControllerAdvice
class GraphQlErrorHandler {

    @GraphQlExceptionHandler
    GraphQLError handle(BookNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .message("Không tìm thấy sách")
                .errorType(ErrorType.NOT_FOUND)
                .build();
    }
}
~~~

Ví dụ trên tập trung vào cách ánh xạ exception; import và kiểu error code cụ thể cần phù hợp với phiên bản Spring GraphQL và quy ước lỗi của ứng dụng.

Không nên bắt mọi exception rồi trả về một response thành công giả. Nếu che giấu lỗi hệ thống, log và giám sát sẽ khó xác định nguyên nhân. Hãy phân loại lỗi nghiệp vụ có thể công bố cho client với lỗi nội bộ cần được ghi nhận và xử lý an toàn.

Execution service không phải nơi thích hợp để tự tạo thông báo lỗi cho từng nghiệp vụ. Nó có thể quan sát kết quả thực thi ở cấp tổng thể; resolver và exception resolver hiểu rõ ngữ nghĩa của field và exception hơn.

## 10. Kiểm thử execution service

Spring for GraphQL cung cấp các tester ở những tầng khác nhau. Nếu mục tiêu là kiểm tra GraphQL execution mà không cần khởi chạy HTTP server, có thể dùng `ExecutionGraphQlServiceTester`.

Ví dụ:

~~~java
ExecutionGraphQlServiceTester tester =
        ExecutionGraphQlServiceTester.create(executionGraphQlService);

tester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "book-42")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

Test gửi operation và variables vào execution service, sau đó kiểm tra field trong kết quả. Nó phù hợp để xác minh schema, DataFetcher và quá trình thực thi ở tầng service.

Chọn tester theo phạm vi cần xác minh:

| Tester | Phạm vi kiểm thử |
| --- | --- |
| `ExecutionGraphQlServiceTester` | Thực thi GraphQL qua execution service |
| `WebGraphQlTester` | Chuỗi xử lý ở tầng web GraphQL, bao gồm interceptor |
| `HttpGraphQlTester` | Request/response qua HTTP endpoint |
| `WebSocketGraphQlTester` | Tương tác qua WebSocket |
| `RSocketGraphQlTester` | Tương tác qua RSocket |

Ví dụ, nếu cần xác minh interceptor đọc header và đưa tenant vào GraphQL context, test trực tiếp execution service có thể bỏ qua interceptor. Khi đó nên kiểm thử ở tầng `WebGraphQlHandler` hoặc HTTP tester để bảo đảm toàn bộ chuỗi xử lý hoạt động.

Một bộ test hợp lý có thể bao gồm:

- Operation hợp lệ với variables hợp lệ.
- Field không tồn tại hoặc variables sai kiểu.
- Resolver trả dữ liệu thành công.
- Resolver phát sinh exception và exception được ánh xạ đúng.
- Context được interceptor bổ sung có thể truy cập từ resolver.
- Response có partial data khi một field lỗi nhưng các field khác vẫn thực thi được.
- Subscription được kiểm tra qua transport và tester phù hợp nếu ứng dụng có sử dụng.

## 11. Hiệu năng, bảo mật và vận hành

Execution service là ranh giới thuận tiện để quan sát một lần thực thi GraphQL, nhưng hiệu năng và bảo mật còn phụ thuộc nhiều tầng khác.

### 11.1. Đo lường

Các chỉ số có thể hữu ích:

- Số lần thực thi theo operation name.
- Thời gian thực thi ở cấp request.
- Số lỗi theo loại hoặc mã lỗi đã chuẩn hóa.
- Tỷ lệ request bị hủy hoặc timeout.
- Phân bố độ sâu và độ phức tạp query nếu ứng dụng có cơ chế đo lường tương ứng.

Không nên chỉ dùng operation name làm nhãn metrics nếu client có thể gửi tên tùy ý với số lượng rất lớn. Nên giới hạn cardinality bằng danh sách operation đã biết hoặc chuẩn hóa nhãn.

### 11.2. Bảo vệ dữ liệu trong log

Document và variables có thể chứa thông tin cá nhân, token hoặc dữ liệu nghiệp vụ. Trước khi ghi log, cần xác định dữ liệu nào được phép lưu, dữ liệu nào phải che hoặc loại bỏ.

Nên ưu tiên correlation ID, operation name đã chuẩn hóa, thời gian xử lý và mã lỗi. Không ghi access token, session ID hoặc toàn bộ variables vào log chỉ để thuận tiện debug.

### 11.3. Giới hạn tài nguyên

Một execution service có thể nhận operation yêu cầu nhiều field lồng nhau hoặc một lượng dữ liệu lớn. Việc giới hạn query depth, query complexity, timeout, pagination và kích thước request thường cần được thiết kế ở những extension point tương ứng của GraphQL engine và transport.

Execution service không tự động giải quyết N+1. Để giảm số lần truy vấn dữ liệu, ứng dụng cần thiết kế resolver hợp lý và sử dụng DataLoader, `BatchLoaderRegistry` hoặc `@BatchMapping` khi phù hợp.

### 11.4. Bảo mật theo request và theo field

Xác thực ở tầng web giúp xác định danh tính request. Phân quyền có thể cần được kiểm tra tại service nghiệp vụ hoặc resolver của từng field, tùy quy tắc dữ liệu.

Đưa thông tin người dùng vào GraphQL context không tự tạo ra bảo mật. Resolver vẫn phải kiểm tra người dùng có quyền truy cập đối tượng hoặc thao tác được yêu cầu hay không. Đặc biệt, không được tin tenant ID, role hoặc user ID do client truyền vào nếu chúng chưa được xác minh.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hiểu đúng |
| --- | --- |
| `ExecutionGraphQlService` là controller nhận HTTP | Đây là service thực thi GraphQL request; transport và web handler xử lý HTTP |
| `GraphQlSource` và execution service là một | Source cung cấp runtime; service sử dụng runtime để thực thi request |
| Mỗi field cần được viết trong execution service | Field được resolve bởi DataFetcher hoặc controller đã đăng ký với schema |
| Muốn đọc header phải sửa execution service | Dùng `WebGraphQlInterceptor` ở tầng web |
| Mọi exception đều nên bắt trong execution service | Dùng exception resolver hoặc `@GraphQlExceptionHandler` cho lỗi DataFetcher |
| Trả về `Mono` nghĩa là Subscription không có stream | `Mono` là kết quả bất đồng bộ của lời gọi service; subscription có ngữ nghĩa stream riêng |
| Thay implementation mặc định sẽ làm GraphQL nhanh hơn | Chỉ thay khi có yêu cầu cụ thể và có đo lường chứng minh lợi ích |
| Dùng execution service sẽ tự giải quyết N+1 | N+1 cần được xử lý ở thiết kế resolver và cơ chế batch loading |

## 13. Quy trình làm việc khi cần can thiệp execution service

Khi phát sinh yêu cầu thay đổi ở tầng thực thi, hãy xác định đúng phạm vi trước khi sửa:

1. **Xác định điểm phát sinh yêu cầu.** Vấn đề nằm ở transport, web request, context, GraphQL engine hay resolver?
2. **Chọn extension point phù hợp.** Dùng interceptor cho metadata web; dùng resolver cho logic field; chỉ dùng execution service khi cần điều phối ở cấp service.
3. **Giữ implementation mặc định nếu có thể.** Chỉ thay hoặc bọc `DefaultExecutionGraphQlService` khi đã có lý do kỹ thuật cụ thể.
4. **Giữ luồng reactive.** Không chặn kết quả bằng `block()` trong request path.
5. **Kiểm tra kết quả và lỗi.** Bảo đảm response giữ đúng semantics của GraphQL, bao gồm partial data và errors.
6. **Kiểm thử đúng tầng.** Service tester cho execution; web hoặc transport tester cho interceptor và giao thức.
7. **Quan sát sau triển khai.** Đo latency, lỗi và mức sử dụng tài nguyên; bảo vệ dữ liệu nhạy cảm trong log.

## 14. Tổng kết

`ExecutionGraphQlService` là abstraction trung tâm cho việc thực thi GraphQL request trong Spring for GraphQL. Nó nhận `ExecutionGraphQlRequest`, sử dụng GraphQL runtime được cung cấp bởi `GraphQlSource` và trả về `ExecutionGraphQlResponse` theo mô hình reactive.

Trong ứng dụng Spring Boot thông thường, `DefaultExecutionGraphQlService` đáp ứng phần lớn nhu cầu và được cấu hình tự động. Khi cần mở rộng, hãy chọn đúng tầng: `WebGraphQlInterceptor` cho metadata và context của web request, DataFetcher hoặc controller cho logic field, exception resolver cho lỗi, instrumentation cho quan sát GraphQL engine. Chỉ tùy chỉnh execution service khi yêu cầu thực sự nằm ở ranh giới điều phối thực thi.

Hiểu rõ ranh giới này giúp ứng dụng giữ được kiến trúc dễ kiểm thử, dễ quan sát và nhất quán giữa schema, operation, resolver và transport.

