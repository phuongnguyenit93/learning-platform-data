# Exception ở DataFetcher

Trong GraphQL, mỗi field được phân giải bởi một **DataFetcher**. DataFetcher có thể gọi repository, service, hệ thống bên ngoài hoặc thực hiện một quy tắc nghiệp vụ. Những thao tác này có thể thất bại: không tìm thấy dữ liệu, người dùng không đủ quyền, dữ liệu vi phạm quy tắc hoặc dịch vụ downstream không phản hồi.

Khi exception xảy ra trong DataFetcher, GraphQL Java chuyển lỗi vào cơ chế xử lý exception của quá trình thực thi field. Spring for GraphQL bổ sung **DataFetcherExceptionResolver** để chuyển exception thành một hoặc nhiều **GraphQLError** có cấu trúc, phù hợp với API. Mục tiêu là trả thông tin đủ hữu ích cho client, giữ lại dữ liệu của những field khác khi có thể và không làm lộ chi tiết nội bộ.

## 1. Exception xảy ra ở đâu trong GraphQL execution?

Một GraphQL operation được parse, validate rồi mới thực thi. Trong giai đoạn execution, GraphQL Java gọi DataFetcher tương ứng với từng field được chọn. Với Spring for GraphQL, DataFetcher có thể được tạo từ annotated controller như **@QueryMapping**, **@MutationMapping**, **@SchemaMapping**, hoặc được đăng ký trực tiếp.

Ví dụ resolver đọc một quyển sách:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

Nếu **bookService.findById** ném **BookNotFoundException**, exception xảy ra trong quá trình DataFetcher của field **Query.bookById** đang chạy. GraphQL Java ghi nhận lỗi cho field đó, gắn vị trí và path tương ứng, rồi tiếp tục thực thi những field khác theo quy tắc GraphQL nếu có thể.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[GraphQL request] --> B[Parse và validate]
    B --> C[Execute selection set]
    C --> D[Invoke DataFetcher]
    D --> E{Có exception?}
    E -->|Không| F[Đưa data vào response]
    E -->|Có| G[DataFetcherExceptionHandler]
    G --> H[Spring DataFetcherExceptionResolver]
    H --> I[GraphQLError]
    I --> J[Thêm errors và áp dụng null propagation]
    F --> K[GraphQL response]
    J --> K
~~~

Exception từ DataFetcher khác với lỗi cú pháp hoặc lỗi validation của GraphQL document. Lỗi parse/validation xảy ra trước khi DataFetcher chạy; vì vậy **DataFetcherExceptionResolver** không phải nơi xử lý mọi lỗi có thể xuất hiện trong GraphQL request.

## 2. Các loại lỗi cần phân biệt

Không phải exception nào cũng nên được trả cho client theo cùng một cách. Trước khi viết resolver, hãy phân loại lỗi theo nguồn gốc và ý nghĩa API:

| Loại lỗi | Ví dụ | Cách xử lý thường phù hợp |
| --- | --- | --- |
| Không tìm thấy tài nguyên | Không có sách với ID đã truyền | Trả lỗi nghiệp vụ có mã ổn định, hoặc null nếu contract cho phép và đó là cách API định nghĩa |
| Không được phép | Người dùng đã xác thực nhưng không có quyền xem đơn hàng | Trả lỗi FORBIDDEN, không tiết lộ dữ liệu bị bảo vệ |
| Chưa xác thực | Không có principal hoặc token hợp lệ | Xử lý ở security layer hoặc trả lỗi UNAUTHORIZED theo hợp đồng API |
| Input không hợp lệ | Giá trị vượt giới hạn nghiệp vụ | Trả lỗi BAD_REQUEST hoặc mã validation riêng |
| Xung đột nghiệp vụ | Đơn hàng đã được xác nhận, không thể sửa | Trả mã lỗi nghiệp vụ như ORDER_ALREADY_CONFIRMED |
| Hạ tầng/downstream | Database hoặc dịch vụ thanh toán không khả dụng | Log đầy đủ ở server, trả lỗi tổng quát an toàn |
| Lỗi lập trình | Null ngoài dự kiến, invariant bị phá vỡ | Xem là lỗi nội bộ, không đưa chi tiết exception ra client |

GraphQL schema đã kiểm tra kiểu dữ liệu, required argument, enum và scalar coercion trước khi DataFetcher chạy. Tuy nhiên, những quy tắc như số lượng phải dương, tài khoản phải thuộc tenant hiện tại hoặc trạng thái đơn hàng phải cho phép chuyển đổi vẫn cần được kiểm tra ở tầng ứng dụng/domain.

Không nên dùng exception cho mọi nhánh điều khiển thông thường. Nếu không tìm thấy một kết quả nullable và đó là trạng thái bình thường của API, resolver có thể trả null. Nếu tình huống mang ý nghĩa lỗi nghiệp vụ mà client cần phân biệt, hãy trả GraphQL error với mã ổn định.

## 3. GraphQL response khi DataFetcher gặp exception

GraphQL không nhất thiết hủy toàn bộ operation khi một field gặp lỗi. Response execution có thể chứa cả **data** và **errors**:

~~~json
{
  "data": {
    "bookById": null,
    "latestBooks": [
      {
        "id": "book-01",
        "title": "Spring in Action"
      }
    ]
  },
  "errors": [
    {
      "message": "Book not found",
      "locations": [
        { "line": 2, "column": 3 }
      ],
      "path": ["bookById"]
    }
  ]
}
~~~

Trong ví dụ, field **bookById** thất bại nhưng **latestBooks** vẫn có dữ liệu. Đây là partial response. Client cần kiểm tra cả data và errors thay vì chỉ dựa vào HTTP status hoặc giả định một request chỉ có thể thành công hoàn toàn hay thất bại hoàn toàn.

Một GraphQL error thường có các thành phần:

- **message**: thông điệp dành cho client.
- **locations**: vị trí field trong GraphQL document, nếu có.
- **path**: đường dẫn đến field phát sinh lỗi trong response.
- **extensions**: metadata bổ sung như mã lỗi, classification hoặc thông tin có thể công khai.

Path sử dụng response key nên có thể chứa alias và chỉ số list. Ví dụ client gọi alias **featured: bookById** và lỗi xảy ra ở phần tử thứ ba của list, path có thể là **["featured", "reviews", 2, "author"]**. Dựa vào path, client xác định chính xác phần dữ liệu bị ảnh hưởng.

## 4. DataFetcherExceptionHandler mặc định của GraphQL Java

GraphQL Java có cơ chế **DataFetcherExceptionHandler** để nhận exception phát sinh khi DataFetcher được thực thi và chuyển chúng thành lỗi thực thi. Handler mặc định ghi nhận exception cùng vị trí/path field, sau đó tạo GraphQLError tương ứng.

Khi dùng Spring for GraphQL, framework tích hợp cơ chế xử lý lỗi này với danh sách **DataFetcherExceptionResolver**. Các resolver của ứng dụng có cơ hội nhận diện exception và tạo lỗi phù hợp. Nếu không resolver nào xử lý exception, Spring dùng hành vi mặc định: ghi log lỗi và trả thông báo tổng quát, tránh phơi bày chi tiết nội bộ cho client.

Điều này tạo ra hai trách nhiệm riêng:

1. GraphQL Java xác định lỗi thuộc field nào và tiếp tục thực thi theo semantics GraphQL.
2. Spring for GraphQL cho phép ứng dụng diễn giải exception thành GraphQLError phù hợp với contract của API.

Không nên tự thay DataFetcherExceptionHandler của GraphQL Java chỉ để đổi message cho một exception nghiệp vụ nếu Spring đã cung cấp extension point **DataFetcherExceptionResolver**. Dùng resolver giúp tích hợp với cấu hình Spring và dễ kiểm thử hơn.

## 5. DataFetcherExceptionResolver

**DataFetcherExceptionResolver** là contract của Spring for GraphQL để xử lý exception từ DataFetcher. Resolver nhận exception và **DataFetchingEnvironment**, sau đó trả về kết quả bất đồng bộ chứa danh sách GraphQLError nếu nhận diện được lỗi.

Khi không xử lý exception, resolver cần báo trạng thái unresolved để resolver tiếp theo hoặc default handler tiếp tục xử lý. Với interface trực tiếp, giá trị **Mono.empty()** thể hiện chưa resolve; khi đã resolve, trả một Mono chứa danh sách lỗi. Không nhầm một danh sách lỗi rỗng với trạng thái unresolved.

Ví dụ triển khai adapter để ánh xạ lỗi không tìm thấy sách:

~~~java
@Component
public class BookNotFoundExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable ex, DataFetchingEnvironment environment) {

        if (ex instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
        }

        return null;
    }
}
~~~

**DataFetcherExceptionResolverAdapter** đơn giản hóa việc triển khai khi một exception chỉ cần tạo một GraphQLError. Phương thức **resolveToSingleError** trả về GraphQLError nếu đã xử lý; trả null nếu exception không thuộc phạm vi resolver này.

**GraphqlErrorBuilder.newError(environment)** giúp tạo error gắn với DataFetchingEnvironment hiện tại. Nhờ đó, GraphQL error có location/path phù hợp với field đang thực thi. **ErrorType.NOT_FOUND** là classification của Spring for GraphQL; extension **code** là mã ổn định do ứng dụng định nghĩa để client xử lý.

Đăng ký resolver bằng component scanning hoặc bean configuration. Spring for GraphQL sẽ dùng các resolver được phát hiện trong quá trình cấu hình GraphQL runtime.

## 6. Phân loại lỗi bằng ErrorType và extensions

Spring for GraphQL cung cấp các classification phổ biến qua **ErrorType**, chẳng hạn:

| ErrorType | Ý nghĩa |
| --- | --- |
| BAD_REQUEST | Input hoặc yêu cầu không hợp lệ ở tầng ứng dụng |
| UNAUTHORIZED | Request chưa được xác thực |
| FORBIDDEN | Người gọi không có quyền thực hiện hành động |
| NOT_FOUND | Tài nguyên được yêu cầu không tồn tại |
| INTERNAL_ERROR | Lỗi nội bộ không nên tiết lộ chi tiết |

Classification giúp client và công cụ quan sát phân loại lỗi. Tuy nhiên, API nên có thêm mã lỗi nghiệp vụ ổn định trong **extensions.code**, ví dụ **BOOK_NOT_FOUND**, **ORDER_ALREADY_CONFIRMED** hoặc **INVENTORY_INSUFFICIENT**. Không nên buộc client phải phân tích chuỗi message vì message có thể thay đổi theo ngôn ngữ hoặc cách diễn đạt.

Ví dụ lỗi xung đột nghiệp vụ:

~~~java
@Component
public class OrderExceptionResolver extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable ex, DataFetchingEnvironment environment) {

        if (ex instanceof OrderAlreadyConfirmedException) {
            return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.BAD_REQUEST)
                .message("The order can no longer be changed")
                .extensions(Map.of("code", "ORDER_ALREADY_CONFIRMED"))
                .build();
        }

        return null;
    }
}
~~~

GraphQL không quy định sẵn mọi mã lỗi nghiệp vụ của ứng dụng. Hãy chọn classification phù hợp và tự định nghĩa extensions cho các trường hợp cần client phân biệt.

## 7. Dùng @GraphQlExceptionHandler

Spring for GraphQL hỗ trợ **@GraphQlExceptionHandler** để xử lý exception bằng annotated method. Có thể đặt handler trong controller để xử lý lỗi gắn với controller đó, hoặc trong **@ControllerAdvice** để áp dụng tập trung cho nhiều controller.

Ví dụ handler toàn cục:

~~~java
@ControllerAdvice
public class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException ex,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(
            AccessDeniedException ex,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.FORBIDDEN)
            .message("You are not allowed to access this resource")
            .extensions(Map.of("code", "ACCESS_DENIED"))
            .build();
    }
}
~~~

Annotated exception handler giúp tổ chức logic theo kiểu exception và tận dụng cơ chế method argument resolution của Spring. Nó phù hợp khi muốn gom các quy tắc ánh xạ lỗi vào controller advice. Với logic phức tạp, cần trả nhiều GraphQLError hoặc cần xử lý ở mức thấp hơn, có thể triển khai **DataFetcherExceptionResolver** trực tiếp hoặc kế thừa adapter.

Không cần viết đồng thời một @GraphQlExceptionHandler và một DataFetcherExceptionResolver cho cùng exception nếu không có chủ đích. Tránh để hai nơi cùng xử lý một lỗi theo hai message hoặc error code khác nhau. Hãy chọn một nơi làm nguồn chính cho từng nhóm exception và kiểm thử thứ tự/độ ưu tiên nếu có nhiều resolver.

## 8. Ánh xạ exception theo nhóm lỗi

Một resolver có thể xử lý nhiều loại exception, nhưng không nên biến thành một khối switch khổng lồ chứa toàn bộ nghiệp vụ. Có thể chia theo nhóm domain hoặc dùng nhiều resolver chuyên biệt.

Ví dụ:

~~~java
@Component
public class AccessExceptionResolver extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable ex, DataFetchingEnvironment environment) {

        if (ex instanceof AccessDeniedException) {
            return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.FORBIDDEN)
                .message("Access denied")
                .extensions(Map.of("code", "ACCESS_DENIED"))
                .build();
        }

        if (ex instanceof AuthenticationException) {
            return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.UNAUTHORIZED)
                .message("Authentication is required")
                .extensions(Map.of("code", "UNAUTHENTICATED"))
                .build();
        }

        return null;
    }
}
~~~

Khi phân loại lỗi bảo mật, phân biệt người gọi chưa được xác thực với người gọi đã xác thực nhưng không đủ quyền. Không trả thông tin cho biết resource nhạy cảm có tồn tại hay không nếu điều đó làm lộ dữ liệu. Trong nhiều hệ thống, cùng một thông điệp chung có thể phù hợp cho cả trường hợp resource không tồn tại và không được phép xem.

Lỗi authentication xảy ra trước khi GraphQL execution bắt đầu có thể được xử lý bởi Spring Security filter hoặc web security layer, không đi qua DataFetcherExceptionResolver. Resolver này chủ yếu xử lý exception phát sinh khi DataFetcher thực thi.

## 9. Exception trong CompletableFuture và resolver bất đồng bộ

DataFetcher có thể trả về **CompletableFuture**, **CompletionStage**, **Mono** hoặc kiểu kết quả bất đồng bộ khác được Spring for GraphQL hỗ trợ. Nếu future hoàn tất bất thường, lỗi vẫn thuộc quá trình thực thi field và được đưa qua cơ chế xử lý exception của GraphQL.

Ví dụ:

~~~java
@QueryMapping
public CompletableFuture<Book> bookById(@Argument("id") String id) {
    return bookClient.findById(id);
}
~~~

Nếu lời gọi HTTP hoàn tất với exception, resolver exception có thể nhận lỗi tương ứng và tạo GraphQLError cho field **bookById**. Với CompletableFuture, exception có thể được bọc trong **CompletionException**; khi cần nhận diện nguyên nhân, hãy kiểm tra cause một cách an toàn thay vì giả định exception luôn là lớp ngoài cùng.

Không gọi **join()** hoặc **get()** trong controller chỉ để bắt exception đồng bộ. Cách đó chặn thread và làm mất lợi ích async. Hãy để future hoàn tất bất thường và xử lý ở DataFetcherExceptionResolver hoặc annotated exception handler.

Với resolver trả Mono/Flux, lỗi reactive cũng cần được chuyển theo cơ chế tương thích của Spring for GraphQL. Tránh tự đổi lỗi thành null hoặc danh sách rỗng nếu đó không phải fallback hợp lệ của nghiệp vụ.

## 10. Path, location và alias trong GraphQLError

Khi dùng **GraphqlErrorBuilder.newError(environment)**, GraphQL Java có thể gắn thông tin execution vào lỗi:

- Location chỉ ra dòng/cột trong document tại field đang được thực thi.
- Path chỉ ra vị trí trong response data.
- Alias được dùng làm response key trong path.
- Index của list xuất hiện trong path khi lỗi xảy ra ở phần tử cụ thể.

Ví dụ query:

~~~graphql
query {
    featured: bookById(id: "missing") {
        author {
            name
        }
    }
}
~~~

Nếu lỗi phát sinh ở **Book.author**, path có thể bắt đầu bằng **["featured", "author"]**. Client dùng path để xác định nhánh bị lỗi ngay cả khi alias khác tên field trong schema.

Không nên tự tạo error mà bỏ mất environment khi lỗi gắn với một field cụ thể. Dùng builder nhận DataFetchingEnvironment giúp giữ path/location đúng. Với lỗi không gắn với một field, chẳng hạn lỗi parse/validation hoặc lỗi request ở tầng transport, cách tạo error và vị trí xử lý sẽ khác.

## 11. Null propagation khi field non-null gặp lỗi

GraphQL schema định nghĩa field nullable hay non-null. Khi DataFetcher của field non-null gặp exception, GraphQL không thể trả null ngay tại field đó mà vẫn giữ contract. Null được đẩy lên parent gần nhất có thể nhận null; quá trình này gọi là **null propagation**.

Ví dụ:

~~~graphql
type Query {
    book: Book
}

type Book {
    id: ID!
    author: Author!
}

type Author {
    name: String!
}
~~~

Nếu **Book.author** lỗi, giá trị author không thể null vì schema khai báo Author!. Vì **Query.book** nullable, toàn bộ book có thể trở thành null. GraphQL vẫn giữ error path chỉ đến field author ban đầu.

Nếu cả **Query.book** cũng là Book! thì null tiếp tục lan lên root data. Vì vậy, một exception ở field sâu có thể khiến một phần lớn response bị null tùy theo chuỗi non-null wrapper.

Khi thiết kế schema, hãy chọn nullability theo khả năng dữ liệu và mức độ độc lập của các field. Không đánh dấu mọi field là non-null chỉ để response trông gọn hơn. Nếu một field phụ thuộc dịch vụ không ổn định, nullable có thể giúp các field khác vẫn trả dữ liệu.

## 12. Partial data và xử lý phía client

Client nên xử lý đồng thời hai phần của GraphQL response:

- **data** chứa những field đã phân giải thành công hoặc null do lỗi/nullability.
- **errors** chứa thông tin lỗi, path và extensions.

Ví dụ một màn hình hiển thị thông tin sách và đánh giá. Nếu service đánh giá lỗi, client có thể vẫn hiển thị tiêu đề sách và thông báo phần đánh giá tạm thời không khả dụng, miễn schema cho phép field reviews nullable.

Không nên coi việc có phần tử trong errors đồng nghĩa toàn bộ operation thất bại. Ngược lại, không nên bỏ qua errors chỉ vì data vẫn có một phần. Client có thể dựa vào extensions.code để quyết định hiển thị thông báo, yêu cầu đăng nhập lại hoặc cho phép retry một phần dữ liệu.

HTTP status của request GraphQL phụ thuộc transport và cấu hình xử lý request/execution. Execution error không nhất thiết tương ứng một HTTP 4xx/5xx cho toàn bộ request. Vì vậy, mã lỗi trong GraphQL extensions là hợp đồng rõ ràng hơn cho xử lý lỗi theo field.

## 13. Validation error và exception ở DataFetcher khác nhau

Cần phân biệt lỗi xảy ra trước execution và lỗi trong DataFetcher:

| Giai đoạn | Ví dụ | DataFetcherExceptionResolver xử lý? |
| --- | --- | --- |
| Parse | GraphQL document sai cú pháp | Không |
| Validation | Field không tồn tại, argument sai kiểu | Không |
| Variable coercion | Variable không tương thích scalar hoặc thiếu variable non-null | Không |
| DataFetcher execution | Service ném BookNotFoundException | Có |
| Async completion | CompletableFuture hoàn tất bất thường trong resolver | Có |
| HTTP authentication/filter | Token không hợp lệ trước GraphQL handler | Thường xử lý ở security/web layer |

Bean Validation trên DTO hoặc input có thể chạy trong lúc resolver được gọi. Nếu validation exception được ném từ method hoặc service, nó có thể được xử lý như exception của DataFetcher. Nhưng lỗi GraphQL type coercion đã xảy ra trước đó không đi qua resolver.

Hãy chọn extension point đúng tầng. Dùng schema để kiểm tra kiểu và required input; dùng Bean Validation/domain service cho quy tắc dữ liệu; dùng DataFetcherExceptionResolver cho exception phát sinh trong quá trình phân giải field.

## 14. Logging và bảo vệ thông tin nội bộ

Exception thường chứa thông tin hữu ích cho developer nhưng không phù hợp để trả nguyên văn cho client. Ví dụ thông điệp từ JDBC driver có thể chứa tên bảng, SQL, host database; HTTP client có thể đưa URL nội bộ hoặc token vào exception; stack trace có thể tiết lộ class và cấu trúc hệ thống.

Nguyên tắc:

- Trả message ngắn, an toàn và có ý nghĩa với client.
- Đưa mã lỗi ổn định vào extensions.code.
- Log exception gốc ở server với stack trace khi cần điều tra.
- Gắn correlation ID hoặc trace ID vào log để tìm request liên quan.
- Không log token, cookie, password, payment data hoặc toàn bộ GraphQL variables nếu có dữ liệu nhạy cảm.
- Không trả ex.getMessage() cho mọi exception một cách mặc định.
- Không nuốt exception hạ tầng rồi trả dữ liệu rỗng như thể request thành công.

Default handler của Spring for GraphQL giúp che chi tiết lỗi chưa được resolve bằng thông báo tổng quát. Với lỗi nghiệp vụ đã nhận diện, resolver có thể trả message cụ thể nhưng vẫn phải tránh tiết lộ thông tin không cần thiết.

## 15. Kiểm thử DataFetcherExceptionResolver bằng GraphQlTester

Nên kiểm thử từ góc nhìn client GraphQL để xác nhận resolver được gọi, exception được ánh xạ và response có data/errors đúng contract.

Ví dụ query một ID không tồn tại:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            bookById(id: "missing") {
                id
                title
            }
        }
        """)
    .execute();

response.errors()
    .expect(error ->
        "BOOK_NOT_FOUND".equals(error.getExtensions().get("code")))
    .verify();

response.path("bookById").valueIsNull();
~~~

Test này kiểm tra mã lỗi công khai và giá trị field nullable. Nếu schema dùng field non-null, hãy kiểm tra vị trí null propagation theo cấu trúc parent thay vì kỳ vọng field con chỉ null.

Các trường hợp nên kiểm thử:

1. Exception nghiệp vụ được ánh xạ thành đúng classification và error code.
2. Exception không được resolver nhận diện đi đến default handler.
3. Message trả về không chứa SQL, stack trace, host nội bộ hoặc token.
4. Alias và list index được phản ánh đúng trong error path.
5. Field nullable giữ được partial data của các field khác.
6. Field non-null áp dụng null propagation đúng schema.
7. Future/Mono hoàn tất bất thường được xử lý tương tự resolver đồng bộ.
8. Authentication và authorization phân biệt đúng UNAUTHORIZED/FORBIDDEN.
9. Lỗi validation trước execution không bị nhầm là lỗi DataFetcher.

Ngoài integration test, có thể unit test resolver bằng cách cung cấp exception và DataFetchingEnvironment giả lập phù hợp. Tuy nhiên, test qua GraphQlTester vẫn cần thiết để kiểm tra wiring thật của Spring và response cuối cùng.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Client thấy Internal Server Error cho lỗi nghiệp vụ | Chưa đăng ký resolver hoặc exception chưa được nhận diện | Đăng ký DataFetcherExceptionResolver hoặc @GraphQlExceptionHandler |
| Resolver không xử lý lỗi parse/validation | Exception xảy ra trước khi DataFetcher chạy | Xử lý ở GraphQL request/validation layer phù hợp |
| Client thấy message nội bộ | Trả nguyên ex.getMessage() | Dùng message an toàn và log exception gốc phía server |
| Không có path/location mong muốn | Tạo GraphQLError không gắn DataFetchingEnvironment | Dùng GraphqlErrorBuilder.newError(environment) |
| Field cha cũng thành null | Non-null propagation theo schema | Xem lại nullability và contract của field |
| Một resolver bắt exception nhưng resolver khác không chạy | Logic xử lý đặt sai phạm vi hoặc exception không được ném từ DataFetcher | Kiểm tra lifecycle và loại exception thực tế |
| Exception async không được nhận diện | Cause bị bọc trong CompletionException | Kiểm tra cause an toàn khi phân loại |
| Error code thay đổi theo message | Client phụ thuộc chuỗi message | Định nghĩa extensions.code ổn định |
| Cùng lỗi bị xử lý hai lần | Có cả annotated handler và resolver trùng phạm vi | Chọn một nguồn xử lý hoặc kiểm soát thứ tự |
| Lỗi bị biến thành null/rỗng | Fallback che mất exception | Chỉ fallback khi đó là hành vi nghiệp vụ hợp lệ |

## 17. Nguyên tắc thiết kế exception handling

Phân loại exception theo ý nghĩa nghiệp vụ và tầng phát sinh. Dùng **DataFetcherExceptionResolverAdapter** cho các ánh xạ rõ ràng, đơn giản; dùng **@GraphQlExceptionHandler** khi muốn tổ chức handler theo controller hoặc ControllerAdvice; dùng interface **DataFetcherExceptionResolver** khi cần xử lý nhiều lỗi hoặc logic tùy chỉnh sâu hơn.

Tạo GraphQLError gắn với DataFetchingEnvironment để giữ path/location. Chọn ErrorType phù hợp và cung cấp extensions.code ổn định cho client. Giữ message an toàn, log exception gốc ở server và không để lỗi nội bộ làm lộ dữ liệu. Hiểu null propagation để chọn nullability đúng với khả năng field thất bại.

Trong Spring for GraphQL, exception ở DataFetcher là lỗi thực thi theo field. Một resolver tốt không chỉ đổi exception thành message; nó phải giữ semantics của GraphQL, cho phép partial data khi phù hợp và cung cấp hợp đồng lỗi mà client có thể xử lý nhất quán.
