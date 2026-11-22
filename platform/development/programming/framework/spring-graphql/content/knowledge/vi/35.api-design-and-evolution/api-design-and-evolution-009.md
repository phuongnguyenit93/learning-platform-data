# Error contract

Một GraphQL API cần quy ước lỗi ổn định để client biết khi nào request không thể chạy, khi nào chỉ một field thất bại và khi nào một thao tác nghiệp vụ bị từ chối. Trong Spring for GraphQL, lỗi có thể phát sinh ở nhiều giai đoạn: parse và validation, binding argument, DataFetcher, service method hoặc publisher của Subscription. Mỗi loại lỗi đi qua một cơ chế xử lý khác nhau.

Error contract là phần hợp đồng công khai mô tả hình dạng lỗi, mã lỗi, ý nghĩa, khả năng retry và dữ liệu nào có thể xuất hiện cùng partial response. Hợp đồng này giúp client xử lý nhất quán và cho phép server thay đổi implementation mà không làm vỡ ứng dụng tiêu thụ API.

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt request errors, execution errors và lỗi ở tầng transport.
- Đọc các trường `message`, `locations`, `path` và `extensions` trong GraphQL response.
- Hiểu partial data và null propagation theo nullability của SDL.
- Thiết kế `extensions.code` ổn định cho API.
- Phân biệt lỗi kỹ thuật với lỗi nghiệp vụ có thể dự đoán.
- Chọn giữa top-level GraphQL errors và errors-as-data trong schema.
- Ánh xạ exception bằng `DataFetcherExceptionResolver` và `@GraphQlExceptionHandler`.
- Xử lý binding/validation errors, authentication và authorization errors.
- Biết giới hạn của DataFetcherExceptionResolver đối với request errors và Subscription publisher errors.
- Chuẩn hóa message, logging, correlation ID và thông tin nhạy cảm.
- Kiểm thử error contract bằng `GraphQlTester`.
- Tiến hóa mã lỗi mà không phá vỡ client hiện có.

## 1. Error contract là gì?

GraphQL response không chỉ chứa dữ liệu thành công. Một response có thể chứa dữ liệu một phần và danh sách lỗi. Vì vậy, client cần hiểu rõ:

- Request có được thực thi hay chưa?
- Field nào phát sinh lỗi?
- Field đó được thay bằng null hay null đã lan truyền lên parent?
- Lỗi thuộc loại nào?
- Client có thể thử lại hay cần thay đổi input?
- Có dữ liệu nào vẫn dùng được trong response không?

Một response thành công đơn giản:

~~~json
{
  "data": {
    "bookById": {
      "id": "b-100",
      "title": "GraphQL in Practice"
    }
  }
}
~~~

Một response có execution error:

~~~json
{
  "data": {
    "bookById": {
      "id": "b-100",
      "title": null
    }
  },
  "errors": [
    {
      "message": "Book title is temporarily unavailable",
      "path": ["bookById", "title"],
      "extensions": {
        "code": "BOOK_TITLE_UNAVAILABLE"
      }
    }
  ]
}
~~~

Client vẫn có thể sử dụng ID của Book dù field title bị lỗi. Đây là khác biệt quan trọng giữa GraphQL và một API chỉ trả một status/error body cho toàn request.

Error contract nên được thiết kế có chủ đích thay vì để mỗi resolver tự tạo message và extension theo một kiểu khác nhau.

## 2. Hình dạng GraphQL response

GraphQL response có ba top-level entries được chuẩn hóa:

| Entry | Vai trò |
|---|---|
| `data` | Kết quả thực thi operation |
| `errors` | Danh sách lỗi xảy ra trong request |
| `extensions` | Metadata mở rộng do implementation cung cấp |

Response thành công thường có `data` và không có `errors`. Theo GraphQL Specification hiện hành, request error result có `errors` nhưng không có `data`. Khi lỗi xảy ra trong quá trình thực thi field, response có `data` cùng `errors`; giá trị tại vị trí lỗi được thay bằng null và các field khác có thể tiếp tục.

Lưu ý tương thích: tài liệu Spring for GraphQL hiện mô tả request-level parse/validation errors có thể trả `data: null` cùng errors toàn cục. Vì vậy, khi làm việc với một phiên bản Spring for GraphQL/GraphQL Java cụ thể, hãy kiểm tra response thực tế của transport và ghi rõ hành vi trong contract của ứng dụng. Điểm phân biệt cốt lõi vẫn là lỗi xảy ra trước execution và không có field path, thay vì chỉ dựa vào việc key `data` có xuất hiện hay không.

Ví dụ request error:

~~~json
{
  "errors": [
    {
      "message": "Cannot query field 'titel' on type 'Book'.",
      "locations": [
        {
          "line": 3,
          "column": 5
        }
      ]
    }
  ]
}
~~~

Không có `data` vì operation chưa được thực thi.

Ví dụ execution error:

~~~json
{
  "data": {
    "bookById": null,
    "featuredBooks": [
      {
        "id": "b-100",
        "title": "GraphQL in Practice"
      }
    ]
  },
  "errors": [
    {
      "message": "Book not found",
      "locations": [
        {
          "line": 2,
          "column": 3
        }
      ],
      "path": ["bookById"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

Field `featuredBooks` vẫn có dữ liệu. Client cần đọc cả `data` lẫn `errors`, không coi sự xuất hiện của `errors` là toàn bộ operation thất bại.

## 3. Phân biệt request error và execution error

Hai nhóm lỗi có vị trí và cách xử lý khác nhau:

| Đặc điểm | Request error | Execution error |
|---|---|---|
| Thời điểm | Trước khi execute operation | Trong lúc resolve field |
| Ví dụ | Syntax error, unknown field, invalid variable | Record không tồn tại, database timeout |
| Có gọi DataFetcher không? | Không | Có thể đã gọi một hoặc nhiều DataFetcher |
| Top-level `data` | Không có theo spec; một số implementation trả `null` | Có, có thể là object, partial data hoặc null |
| `path` | Thường không có | Xác định response position bị lỗi |
| Cơ chế Spring thường dùng | Transport/interceptor và GraphQL engine | DataFetcherExceptionResolver |

Request errors thường phát sinh khi:

- GraphQL document sai cú pháp.
- Field hoặc argument không tồn tại trong schema.
- Operation không xác định được.
- Variable không thể được coercion theo kiểu khai báo.
- Validation rule từ chối document.

Execution errors có thể phát sinh khi:

- Resolver ném exception.
- Service không tìm thấy dữ liệu.
- Database hoặc downstream service gặp lỗi.
- Giá trị trả về không thể hoàn tất theo output type.
- Authorization từ chối field trong quá trình resolve.

Đừng dùng một resolver exception handler để xử lý mọi loại lỗi. `DataFetcherExceptionResolver` xử lý exception từ DataFetcher trong execution; nó không xử lý lỗi parse/validation xảy ra trước khi DataFetcher được gọi.

## 4. Ý nghĩa của các trường trong errors[]

Mỗi error thường có các trường sau:

| Trường | Ý nghĩa | Có nên dựa vào để điều khiển UI? |
|---|---|---|
| `message` | Mô tả lỗi dành cho developer | Không nên dùng làm mã điều kiện |
| `locations` | Vị trí trong GraphQL document | Chủ yếu dùng debug |
| `path` | Response path nơi lỗi xảy ra | Có thể dùng để xác định field bị ảnh hưởng |
| `extensions` | Metadata mở rộng | Dùng `code` ổn định để phân loại |

Ví dụ:

~~~json
{
  "message": "Book not found",
  "locations": [
    {
      "line": 4,
      "column": 7
    }
  ],
  "path": ["recentBooks", 2, "author"],
  "extensions": {
    "code": "AUTHOR_NOT_FOUND"
  }
}
~~~

`path` dùng response name, do đó alias xuất hiện trong path thay cho tên field gốc. Nếu client gửi:

~~~graphql
query {
  primaryBook: bookById(id: "missing") {
    title
  }
}
~~~

Path của lỗi ở root field là:

~~~json
["primaryBook"]
~~~

Với list, path có thể chứa index dạng number. Vì vậy, client nên xử lý path như một mảng gồm string và integer, không giả định mọi phần tử đều là string.

## 5. Null propagation ảnh hưởng error contract

Khi execution error xảy ra, GraphQL xử lý response position đó như thể field trả về null. Nếu field nullable, parent có thể tiếp tục trả dữ liệu. Nếu field non-null, lỗi lan truyền lên parent cho tới khi gặp một response position nullable hoặc tới root.

Ví dụ SDL:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  author: Author!
}

type Author {
  name: String!
}
~~~

Nếu resolver của `Author.name` lỗi:

- `name` là non-null nên không thể giữ null ở đó.
- `author` cũng non-null nên null tiếp tục lan lên Book.
- `bookById` nullable nên kết quả field bookById trở thành null.
- Các field sibling khác của Query vẫn có thể trả dữ liệu.

Response minh họa:

~~~json
{
  "data": {
    "bookById": null,
    "health": "UP"
  },
  "errors": [
    {
      "message": "Author service unavailable",
      "path": ["bookById", "author", "name"],
      "extensions": {
        "code": "AUTHOR_SERVICE_UNAVAILABLE"
      }
    }
  ]
}
~~~

Nếu `bookById` cũng là `Book!`, null có thể tiếp tục lan lên root và `data` trở thành null. Vì vậy, nullability trong SDL là một phần của error contract, không chỉ là mô tả kiểu dữ liệu.

Khi thiết kế field nhạy cảm hoặc field phụ thuộc service ngoài, hãy cân nhắc liệu lỗi của field đó có nên làm mất toàn bộ parent object hay không.

## 6. Chọn top-level errors hay errors-as-data?

Không phải mọi tình huống không thành công đều nên được biểu diễn bằng exception.

Một quy tắc thực tế:

- Dùng top-level `errors` cho lỗi thực thi bất thường, lỗi hệ thống, lỗi xác thực/ủy quyền và lỗi khiến field không thể được resolve.
- Dùng errors-as-data cho kết quả nghiệp vụ dự đoán được mà client cần xử lý như một phần của workflow.

Ví dụ:

| Tình huống | Cách biểu diễn thường phù hợp |
|---|---|
| Database timeout | Top-level GraphQL error |
| GraphQL document sai | Request error |
| JWT không hợp lệ | HTTP authentication error hoặc GraphQL error tùy lớp từ chối |
| User không có quyền đọc field | Execution error |
| Tên sách đã được sử dụng | Typed business error trong mutation payload |
| Số lượng tồn không đủ | Typed business error trong mutation payload |
| Input không hợp lệ theo quy tắc nghiệp vụ | Typed business error hoặc binding error tùy giai đoạn |

Không dùng top-level exception cho mọi lỗi nghiệp vụ thông thường. Nếu client cần hiển thị danh sách field validation hoặc cho phép người dùng sửa form, typed payload thường rõ ràng hơn.

Ngược lại, không chuyển database outage hoặc lỗi lập trình thành `userErrors`. Client có thể hiểu nhầm đó là kết quả nghiệp vụ có thể xử lý bình thường.

## 7. Thiết kế errors-as-data cho Mutation

Giả sử tạo Book có thể thất bại vì ISBN đã tồn tại hoặc tiêu đề không hợp lệ. Schema có thể khai báo:

~~~graphql
enum CreateBookErrorCode {
  ISBN_ALREADY_EXISTS
  TITLE_REQUIRED
  INVALID_PUBLICATION_YEAR
}

type UserError {
  code: CreateBookErrorCode!
  message: String!
  field: [String!]
}

type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
}

type Mutation {
  createBook(input: CreateBookInput!): CreateBookPayload!
}
~~~

Resolver trả kết quả nghiệp vụ:

~~~java
@MutationMapping
public CreateBookPayload createBook(
        @Argument CreateBookInput input) {

    if (bookService.isbnExists(input.isbn())) {
        return new CreateBookPayload(
                null,
                List.of(new UserError(
                        CreateBookErrorCode.ISBN_ALREADY_EXISTS,
                        "ISBN is already registered",
                        List.of("isbn"))));
    }

    Book book = bookService.create(input);

    return new CreateBookPayload(book, List.of());
}
~~~

Client có thể query payload:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    book {
      id
      title
    }
    userErrors {
      code
      message
      field
    }
  }
}
~~~

Khi ISBN đã tồn tại, operation vẫn thực thi thành công theo GraphQL protocol. Client nhận payload có `book: null` và một phần tử `userErrors`.

Các code trong enum là một phần schema contract. Nếu muốn thêm business error mới, thêm enum value và cập nhật client tương ứng. Tránh đổi ý nghĩa của code cũ hoặc xóa value khi vẫn còn client đang sử dụng.

## 8. Tổ chức error code ổn định

Không để client phụ thuộc vào Java exception class hoặc message tự do.

Ví dụ taxonomy:

| Code | Ý nghĩa | Hướng xử lý client |
|---|---|---|
| `BOOK_NOT_FOUND` | Không tìm thấy Book | Hiển thị empty/not found state |
| `INVALID_INPUT` | Input không hợp lệ | Cho phép sửa dữ liệu |
| `ISBN_ALREADY_EXISTS` | ISBN đã được sử dụng | Báo lỗi tại field ISBN |
| `UNAUTHENTICATED` | Chưa xác thực | Yêu cầu đăng nhập |
| `FORBIDDEN` | Không có quyền | Hiển thị access denied |
| `RATE_LIMITED` | Vượt giới hạn request | Chờ trước khi thử lại |
| `DEPENDENCY_UNAVAILABLE` | Dịch vụ phụ thuộc không sẵn sàng | Có thể retry nếu operation an toàn |
| `INTERNAL_ERROR` | Lỗi không dự kiến | Hiển thị thông báo chung và ghi nhận support ID |

Một code tốt nên:

- Có tên ổn định, dễ đọc.
- Có một ý nghĩa duy nhất.
- Không chứa ID người dùng, ID record hoặc dữ liệu động.
- Không phụ thuộc tên class Java.
- Không thay đổi theo ngôn ngữ hiển thị.
- Được tài liệu hóa cùng hướng xử lý dự kiến.

Có thể thêm metadata trong `extensions`:

~~~json
{
  "code": "DEPENDENCY_UNAVAILABLE",
  "retryable": true,
  "correlationId": "req-7f21"
}
~~~

Chỉ thêm `retryable` khi server có thể đưa ra quyết định đáng tin cậy. Không phải mọi timeout đều có thể retry an toàn, đặc biệt với Mutation đã có thể commit nhưng response bị mất.

## 9. Phân biệt ErrorType với extensions.code

Spring for GraphQL cung cấp `ErrorType` để phân loại lỗi tổng quát:

- `BAD_REQUEST`
- `UNAUTHORIZED`
- `FORBIDDEN`
- `NOT_FOUND`
- `INTERNAL_ERROR`

ErrorType là classification ở mức framework. `extensions.code` là mã chi tiết thuộc public API contract của ứng dụng.

Khi build GraphQLError, đặt `errorType(ErrorType.NOT_FOUND)` để gắn classification của Spring. Nếu muốn công bố classification như một extension riêng, hãy thêm nó rõ ràng vào `extensions`; luôn giữ `extensions.code` làm mã ứng dụng ổn định cho client.

Client có thể dùng code cụ thể để xử lý nghiệp vụ, còn classification giúp nhóm lỗi tổng quát. Không bắt client phân tích `message` để phân biệt not found với forbidden.

`ErrorType` không tự quyết định HTTP status code. Nó phân loại GraphQL error ở tầng execution. HTTP status còn phụ thuộc lỗi xảy ra ở transport hay execution, media type và GraphQL-over-HTTP behavior mà server hỗ trợ. Không ánh xạ máy móc `NOT_FOUND` thành HTTP 404 cho mọi GraphQL field error, vì một response có thể chứa nhiều field và partial data.

Không cần tạo code riêng cho mọi exception class nội bộ. Nhiều exception có thể ánh xạ về cùng một public error code nếu contract và cách xử lý client giống nhau.

## 10. Ánh xạ exception bằng DataFetcherExceptionResolver

Spring for GraphQL đăng ký một DataFetcherExceptionHandler cho GraphQL Java và cung cấp contract `DataFetcherExceptionResolver` để ứng dụng xử lý exception từ DataFetcher.

Spring Boot tự phát hiện các bean resolver và sử dụng chúng theo thứ tự đăng ký. Resolver có thể trả về một hoặc nhiều GraphQLError. Nếu resolver không xử lý exception, nó trả về kết quả unresolved để resolver tiếp theo có cơ hội xử lý.

Ví dụ:

~~~java
@Component
public class BookExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .errorType(ErrorType.NOT_FOUND)
                    .message("Book not found")
                    .extensions(Map.of(
                            "code", "BOOK_NOT_FOUND"))
                    .build();
        }

        if (exception instanceof DependencyUnavailableException) {
            return GraphqlErrorBuilder.newError(environment)
                    .errorType(ErrorType.INTERNAL_ERROR)
                    .message("A required service is temporarily unavailable")
                    .extensions(Map.of(
                            "code", "DEPENDENCY_UNAVAILABLE"))
                    .build();
        }

        return null;
    }
}
~~~

Các điểm cần nhớ:

- Dùng `GraphqlErrorBuilder.newError(environment)` để error gắn với DataFetchingEnvironment hiện tại.
- `ErrorType` phân loại lỗi tổng quát.
- `extensions.code` cung cấp mã ổn định cho client.
- Trả null khi resolver không xử lý exception để resolver tiếp theo được gọi.
- Không đưa exception message nội bộ vào response công khai.

Nếu có nhiều resolver, hãy tổ chức thứ tự để resolver chuyên biệt xử lý exception trước resolver tổng quát.

## 11. Dùng @GraphQlExceptionHandler trong annotated controller

Nếu resolver được khai báo bằng `@QueryMapping`, `@MutationMapping` hoặc `@SchemaMapping`, có thể xử lý exception bằng `@GraphQlExceptionHandler`.

Handler đặt trong controller chỉ áp dụng cho controller đó:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book bookById(@Argument String id) {
        return bookService.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found")
                .extensions(Map.of(
                        "code", "BOOK_NOT_FOUND"))
                .build();
    }
}
~~~

Nếu cần dùng chung cho nhiều controller, đặt handler trong `@ControllerAdvice`:

~~~java
@ControllerAdvice
public class GlobalGraphQlExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleNotFound(
            BookNotFoundException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .errorType(ErrorType.NOT_FOUND)
                .message("Requested resource was not found")
                .extensions(Map.of(
                        "code", "RESOURCE_NOT_FOUND"))
                .build();
    }
}
~~~

Nên inject `GraphqlErrorBuilder` thay vì tự tạo builder không có environment. Builder do Spring cung cấp đã gắn với DataFetchingEnvironment hiện tại, giúp giữ thông tin vị trí field và path.

Không khai báo nhiều handler có thể cùng xử lý một exception mà không có quy tắc rõ ràng. Hãy kiểm tra phạm vi controller và global advice để tránh mapping không nhất quán.

## 12. Binding và validation errors

Có hai thời điểm input có thể bị từ chối:

**GraphQL request validation/coercion**

Nếu client truyền sai kiểu variable, thiếu argument non-null hoặc dùng field không có trong schema, GraphQL có thể từ chối request trước khi DataFetcher chạy. Đây là request error.

**Spring argument binding/Bean Validation**

Khi GraphQL đã chấp nhận operation và Spring bind input vào Java object, validation có thể phát sinh trong lúc DataFetcher được gọi. Ví dụ dùng `@Valid` trên argument:

~~~java
@MutationMapping
public Book createBook(
        @Argument @Valid CreateBookInput input) {
    return bookService.create(input);
}
~~~

DTO:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @NotBlank String isbn,
        @Min(1450) Integer publicationYear) {
}
~~~

Có thể xử lý `BindException` bằng `@GraphQlExceptionHandler`:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleBinding(
        BindException exception,
        GraphqlErrorBuilder<?> errorBuilder) {

    return errorBuilder
            .errorType(ErrorType.BAD_REQUEST)
            .message("Input validation failed")
            .extensions(Map.of(
                    "code", "INVALID_INPUT"))
            .build();
}
~~~

Không trả nguyên văn tất cả rejected values hoặc object input trong message. Chúng có thể chứa email, token, thông tin cá nhân hoặc dữ liệu nhạy cảm. Nếu client cần lỗi theo từng field, errors-as-data với danh sách field path thường phù hợp hơn.

## 13. Request-level errors không đi qua DataFetcherExceptionResolver

Parse, validation và variable coercion errors phát sinh trước khi DataFetcher thực thi. Do đó, `DataFetcherExceptionResolver` không thể xử lý các lỗi này.

Nếu cần chuẩn hóa request errors, có thể dùng `WebGraphQlInterceptor` để quan sát response của GraphQL execution và điều chỉnh error result ở tầng transport.

Không nên thay đổi các thông tin chuẩn như `locations` hoặc `message` đến mức làm mất khả năng debug query. Thông thường chỉ cần bổ sung metadata có ích hoặc áp dụng policy che thông tin ở môi trường production.

Một request-level error không có field path vì chưa có response position nào được thực thi. Client nên hiển thị lỗi tổng quát của operation và dùng locations để hỗ trợ developer khi cần.

## 14. Authentication và authorization errors

Authentication và authorization có thể bị từ chối ở hai lớp:

**HTTP security filter**

Nếu JWT thiếu hoặc không hợp lệ, Spring Security có thể từ chối request trước khi GraphQL engine nhận operation. Client nhận HTTP 401 hoặc 403 theo security configuration và transport.

**Field/service authorization**

Nếu request đã qua HTTP authentication nhưng một DataFetcher gọi service method bị `AccessDeniedException`, đây là execution error. GraphQL có thể trả partial data cùng error tại field bị từ chối.

Ví dụ:

~~~java
@Service
public class InventoryService {

    @PreAuthorize("hasAuthority('SCOPE_inventory:read')")
    public Inventory findForProduct(String productId) {
        return repository.findByProductId(productId)
                .orElseThrow(InventoryNotFoundException::new);
    }
}
~~~

Exception resolver có thể ánh xạ:

~~~java
if (exception instanceof AccessDeniedException) {
    return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.FORBIDDEN)
            .message("Access denied")
            .extensions(Map.of("code", "FORBIDDEN"))
            .build();
}
~~~

Không coi HTTP 200 là bằng chứng mọi field thành công. Một GraphQL execution có thể trả HTTP response thành công ở tầng transport nhưng vẫn có errors trong body. Client cần đọc cả status, content type và GraphQL response.

## 15. Lỗi từ Subscription publisher

Subscription có một lifecycle khác Query và Mutation. DataFetcher của Subscription thường chỉ tạo publisher ban đầu. Sau đó transport subscribe vào publisher và publisher có thể phát lỗi ở thời điểm muộn hơn.

`DataFetcherExceptionResolver` không xử lý lỗi signal phát sinh sau khi DataFetcher đã trả publisher. Spring for GraphQL cung cấp `SubscriptionExceptionResolver` để ánh xạ lỗi từ publisher thành GraphQL errors gửi qua transport.

Ví dụ về contract:

- Lỗi khi tạo publisher có thể đi qua DataFetcher exception handling.
- Lỗi khi publisher đang phát event cần SubscriptionExceptionResolver.
- Client cần xử lý message kết thúc stream hoặc lỗi theo transport protocol.
- Không nên để exception message gốc từ event source đi thẳng tới client.

Với WebSocket, lỗi subscription có thể được gửi như một thông điệp lỗi cuối cùng theo protocol đang dùng. Với SSE, cần kiểm tra cách transport biểu diễn event/error. Không giả định mọi transport có cùng frame format.

## 16. Lỗi ở tầng transport

Một số lỗi không tạo được GraphQL response:

- DNS lookup hoặc TLS handshake thất bại.
- Kết nối bị đóng trước khi server gửi response.
- Client timeout khi chờ response.
- HTTP proxy hoặc gateway từ chối request.
- Request body quá lớn hoặc media type không được hỗ trợ.

Trong các trường hợp này, client có thể không nhận được `data`, `errors` hay `extensions` nào. Đây là transport/network failure, không phải một GraphQL `extensions.code` do resolver trả về. Client cần phân biệt exception của HTTP/WebSocket client với GraphQL errors đã được decode từ response.

Không tự động retry mọi transport failure đối với Mutation. Kết nối có thể bị mất sau khi server đã commit thay đổi nhưng trước khi client nhận response. Dùng idempotency key hoặc command ID nếu client phải có khả năng gửi lại thao tác an toàn.

## 17. Error contract cho lỗi hệ thống và lỗi nội bộ

Không để exception class hoặc message của thư viện xuất hiện trực tiếp trong API contract.

Ví dụ không nên trả:

~~~json
{
  "errors": [
    {
      "message": "org.postgresql.util.PSQLException: Connection refused at 10.0.2.15:5432"
    }
  ]
}
~~~

Thông tin này có thể tiết lộ:

- Công nghệ database.
- Host nội bộ và port.
- Cấu trúc package.
- Tên bảng hoặc query.
- Dữ liệu người dùng.
- Stack trace hoặc chi tiết hạ tầng.

Nên trả message công khai chung:

~~~json
{
  "errors": [
    {
      "message": "The service could not complete the request",
      "extensions": {
        "code": "INTERNAL_ERROR",
        "correlationId": "req-7f21"
      }
    }
  ]
}
~~~

Chi tiết exception được ghi trong server log với correlation/execution ID để đội vận hành tra cứu. Không dùng correlation ID để thay thế authorization hoặc cho phép client đọc log.

## 18. Correlation ID và logging

Một error contract tốt giúp client gửi thông tin đủ để support tìm đúng lỗi trong log.

Có thể dùng các metadata như:

- Correlation ID của HTTP request.
- GraphQL execution ID.
- Operation name.
- Error code.
- Error path.
- Trace ID nếu hệ thống tracing đã cấu hình.

Ví dụ response:

~~~json
{
  "data": {
    "bookById": null
  },
  "errors": [
    {
      "message": "The service could not complete the request",
      "path": ["bookById"],
      "extensions": {
        "code": "DEPENDENCY_UNAVAILABLE",
        "correlationId": "req-7f21"
      }
    }
  ]
}
~~~

Không đưa vào response:

- Bearer token hoặc cookie.
- Password, API key hoặc secret.
- SQL statement và connection string.
- Toàn bộ GraphQL variables.
- Dữ liệu cá nhân không cần thiết.
- Exception message chưa được kiểm soát.

Spring for GraphQL ghi log exception chưa được resolver xử lý ở mức ERROR cùng execution ID để hỗ trợ tương quan. Exception đã được xử lý thường được log ở mức DEBUG. Ứng dụng có thể bổ sung logging policy nhưng cần tránh log cùng một lỗi nhiều lần ở mọi tầng.

## 19. Không dùng message làm API code

Message có thể thay đổi vì:

- Nội dung được viết lại để dễ hiểu hơn.
- Ứng dụng hỗ trợ đa ngôn ngữ.
- Message được điều chỉnh để tránh lộ thông tin.
- Thư viện hoặc framework nâng cấp.

Vì vậy, client không nên làm như sau:

~~~typescript
if (error.message === "Book not found") {
  showNotFound();
}
~~~

Nên dùng code:

~~~typescript
const code = error.extensions?.code;

switch (code) {
  case "BOOK_NOT_FOUND":
    showNotFound();
    break;
  case "FORBIDDEN":
    showAccessDenied();
    break;
  case "DEPENDENCY_UNAVAILABLE":
    showTemporaryFailure();
    break;
  default:
    showGenericError();
}
~~~

Message phục vụ người đọc và debug. Code phục vụ logic máy. Hai giá trị này nên có vòng đời độc lập.

## 20. Retry policy là một phần của error contract

Không phải mọi lỗi đều có thể retry.

| Error code | Có nên retry? | Lý do |
|---|---|---|
| `BOOK_NOT_FOUND` | Không | Dữ liệu không tồn tại |
| `INVALID_INPUT` | Không | Client cần sửa input |
| `FORBIDDEN` | Không | Retry không làm thay đổi quyền |
| `RATE_LIMITED` | Có điều kiện | Chờ theo retry-after/backoff |
| `DEPENDENCY_UNAVAILABLE` | Có điều kiện | Phụ thuộc timeout và trạng thái thao tác |
| `INTERNAL_ERROR` | Không mặc định | Có thể là lỗi logic hoặc trạng thái không xác định |

Với Query đọc dữ liệu, retry có thể an toàn nếu lỗi tạm thời và request không tạo side effect.

Với Mutation, timeout không có nghĩa thao tác chưa commit. Server có thể đã ghi dữ liệu nhưng response bị mất trên mạng. Nếu client gửi lại mutation, thao tác có thể bị lặp.

Để retry Mutation an toàn, cân nhắc:

- Idempotency key.
- Unique business command ID.
- Kiểm tra trạng thái command trước khi thực hiện lại.
- Thiết kế mutation idempotent khi phù hợp.
- Retry có giới hạn, backoff và jitter.

Chỉ trả `retryable: true` khi server có thể cam kết semantics đó.

## 21. Tiến hóa error contract

Error code và payload là API surface. Khi thay đổi, cần tuân thủ quy tắc tương thích:

- Có thể thêm error code mới.
- Có thể thêm extension field tùy chọn nếu client cũ bỏ qua field không biết.
- Không đổi ý nghĩa của code hiện có.
- Không tái sử dụng code đã ngừng dùng cho một lỗi khác.
- Không xóa enum value đang được client sử dụng nếu chưa có migration.
- Không đổi kiểu dữ liệu của extension field hiện hữu.
- Không làm một lỗi nullable trở thành lỗi non-null propagation bất ngờ mà không đánh giá tác động.

Ví dụ code `BOOK_NOT_FOUND` ban đầu có nghĩa không có Book theo ID. Không nên đổi nó thành “Book bị ẩn do policy” nếu client đang hiển thị trang not found cho mọi trường hợp. Hãy tạo code mới hoặc giữ cùng semantics công khai đã cam kết.

Khi thay đổi nullability trong SDL, cần kiểm tra lại partial data và path của lỗi. Một thay đổi từ `Book` sang `Book!` có thể khiến một field error lan truyền lên root và làm mất nhiều dữ liệu hơn trước.

## 22. Error catalog cho API

Với API lớn, nên duy trì error catalog có owner và hướng xử lý.

Ví dụ:

| Code | Phân loại | Nguồn | Hành vi client |
|---|---|---|---|
| `INVALID_INPUT` | BAD_REQUEST | Binding/validation | Hiển thị lỗi form |
| `BOOK_NOT_FOUND` | NOT_FOUND | Book service | Hiển thị not found |
| `FORBIDDEN` | FORBIDDEN | Authorization | Ẩn hoặc khóa hành động |
| `DEPENDENCY_UNAVAILABLE` | INTERNAL_ERROR | Downstream service | Hiển thị lỗi tạm thời |
| `RATE_LIMITED` | BAD_REQUEST hoặc policy riêng | Rate limiter | Backoff |
| `INTERNAL_ERROR` | INTERNAL_ERROR | Unhandled exception | Thông báo chung và support ID |

Catalog nên ghi rõ:

- Code và ý nghĩa.
- Lỗi xuất hiện ở request, execution hay transport layer.
- Có partial data hay không.
- Retry semantics.
- Có correlation ID hay không.
- Dữ liệu nào được phép xuất hiện trong message/extensions.
- Owner chịu trách nhiệm thay đổi code.

Không nhất thiết mọi team phải dùng cùng một danh sách code. Tuy nhiên, các code chung như `FORBIDDEN`, `UNAUTHENTICATED` và `INTERNAL_ERROR` nên có semantics nhất quán trên các subgraph.

## 23. Kiểm thử Error contract bằng GraphQlTester

GraphQlTester cho phép thực thi operation và kiểm tra errors cùng data.

Ví dụ test not found:

~~~java
@Test
void shouldReturnStableNotFoundError() {
    graphQlTester.document("""
            query {
              bookById(id: "missing") {
                id
              }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> {
                assertThat(errors).hasSize(1);
                assertThat(errors.get(0).getMessage())
                        .isEqualTo("Book not found");
                assertThat(errors.get(0).getExtensions())
                        .containsEntry("code", "BOOK_NOT_FOUND");
                assertThat(errors.get(0).getPath())
                        .containsExactly("bookById");
            });
}
~~~

Test partial data:

~~~java
@Test
void shouldKeepSiblingDataWhenOneFieldFails() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
              bookById(id: "b-100") {
                id
                title
              }
              health
            }
            """)
            .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).hasSize(1);
        assertThat(errors.get(0).getExtensions())
                .containsEntry("code", "BOOK_TITLE_UNAVAILABLE");
    });
    response.path("health").entity(String.class).isEqualTo("UP");
}
~~~

Test nên xác nhận cả error code và data. Chỉ kiểm tra `errors().hasSize(1)` chưa đủ để chứng minh client có thể xử lý đúng contract.

## 24. Kiểm thử request errors và execution errors riêng biệt

Request error test:

~~~java
@Test
void shouldRejectInvalidFieldBeforeExecution() {
    graphQlTester.document("""
            query {
              unknownBookField
            }
            """)
            .execute()
            .errors()
            .satisfy(errors ->
                    assertThat(errors).isNotEmpty());
}
~~~

Đối với request error, không có DataFetcher nào được gọi. Có thể verify service không tương tác để bảo đảm query bị từ chối trước execution.

Execution error test:

~~~java
@Test
void shouldReportFieldPathForResolverFailure() {
    graphQlTester.document("""
            query {
              bookById(id: "missing") {
                title
              }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors ->
                    assertThat(errors.get(0).getPath())
                            .containsExactly("bookById"));
}
~~~

Hai test này bảo vệ ranh giới giữa GraphQL engine và DataFetcher exception handling. Nếu code thay đổi khiến request error bị xử lý như execution error hoặc ngược lại, client có thể nhận response khác với contract đã công bố.

## 25. Kiểm thử null propagation

Với field non-null, test cần kiểm tra vị trí data trở thành null sau khi lỗi lan truyền.

Ví dụ SDL:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  author: Author!
}

type Author {
  name: String!
}
~~~

Nếu Author.name lỗi, Book và author có thể bị thay bằng null tùy chuỗi non-null. Test:

~~~java
@Test
void shouldPropagateNonNullFailureToNullableBookField() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
              bookById(id: "b-100") {
                author {
                  name
                }
              }
            }
            """)
            .execute();

    response.errors().satisfy(errors ->
            assertThat(errors.get(0).getPath())
                    .containsExactly("bookById", "author", "name"));
    response.path("bookById").valueIsNull();
}
~~~

Nếu thay đổi SDL nullability, hãy chạy lại test này. Error path vẫn chỉ vị trí phát sinh lỗi; vị trí null cuối cùng có thể ở parent do propagation.

## 26. Kiểm thử message không rò rỉ thông tin nội bộ

Tạo exception giả lập có message chứa thông tin nhạy cảm:

~~~java
throw new IllegalStateException(
        "Database password=secret at db.internal:5432");
~~~

Error contract chỉ nên trả message chung và code:

~~~json
{
  "errors": [
    {
      "message": "The service could not complete the request",
      "extensions": {
        "code": "INTERNAL_ERROR"
      }
    }
  ]
}
~~~

Integration test nên kiểm tra response không chứa:

- Tên class exception nội bộ.
- Connection string hoặc hostname.
- Password/token.
- SQL hoặc stack trace.
- Giá trị GraphQL variables nhạy cảm.

Đồng thời kiểm tra server log vẫn có execution ID hoặc correlation ID để đội vận hành tìm nguyên nhân.

## 27. Những lỗi thiết kế Error contract thường gặp

| Triệu chứng | Nguyên nhân | Cách cải thiện |
|---|---|---|
| Client parse message để biết lỗi | Không có error code ổn định | Dùng `extensions.code` |
| Mọi lỗi đều trả `INTERNAL_ERROR` | Mapping exception quá tổng quát | Phân loại domain và hạ tầng |
| Business validation làm toàn response lỗi | Dùng exception cho kết quả nghiệp vụ dự đoán được | Thiết kế errors-as-data |
| Client bỏ qua partial data | Chỉ kiểm tra errors array | Đọc đồng thời data và errors |
| Request error không được custom resolver bắt | Lỗi xảy ra trước DataFetcher | Dùng transport interceptor khi thực sự cần |
| Subscription lỗi không được ánh xạ | Error signal xảy ra sau khi Publisher được trả về | Dùng SubscriptionExceptionResolver |
| Message lộ SQL hoặc token | Trả exception message gốc | Chuẩn hóa message và log nội bộ |
| Retry Mutation gây ghi trùng | Timeout bị hiểu nhầm là chưa commit | Idempotency key và command ID |
| Field error làm mất toàn object | Nullability quá chặt với field có thể lỗi độc lập | Đánh giá lại SDL nullability |
| HTTP 200 bị hiểu là thành công hoàn toàn | Chỉ đọc status code | Kiểm tra GraphQL errors trong body |
| Error code thay đổi giữa các release | Không có error catalog | Quản lý code như API contract |

## 28. Checklist thiết kế Error contract

Trước khi công bố GraphQL API:

- [ ] Phân biệt request errors, execution errors và transport errors.
- [ ] Dùng đúng `data`, `errors` và `extensions` theo response format.
- [ ] Có error code ổn định cho các lỗi client cần xử lý.
- [ ] Không dùng message làm điều kiện logic.
- [ ] Phân biệt lỗi nghiệp vụ dự đoán được với lỗi hệ thống.
- [ ] Thiết kế errors-as-data cho mutation payload khi phù hợp.
- [ ] Dùng DataFetcherExceptionResolver hoặc @GraphQlExceptionHandler cho lỗi DataFetcher.
- [ ] Có cơ chế xử lý request-level errors nếu cần biến đổi response.
- [ ] Dùng SubscriptionExceptionResolver cho lỗi publisher sau khi subscribe.
- [ ] Đánh giá nullability và null propagation.
- [ ] Error path đúng với alias và list index.
- [ ] Không trả exception message, stack trace hoặc secret.
- [ ] Có correlation/execution ID để support tra cứu.
- [ ] Retry semantics rõ ràng và an toàn với Mutation.
- [ ] Error catalog có owner và được quản lý như API surface.
- [ ] Có test cho request error, execution error, partial data và null propagation.
- [ ] Có test cho message sanitization và stable extensions.code.

## Kết luận

Error contract là một phần của API design. GraphQL phân biệt lỗi trước execution với lỗi xảy ra trong quá trình resolve field. Theo response specification, request errors không có data; một số phiên bản Spring for GraphQL có thể biểu diễn chúng bằng `data: null` như đã lưu ý ở trên. Execution errors có thể trả partial data và error path. Nullability của SDL quyết định lỗi lan truyền tới đâu trong response.

Trong Spring for GraphQL, dùng `DataFetcherExceptionResolver` hoặc `@GraphQlExceptionHandler` để ánh xạ exception từ DataFetcher. Request-level errors cần được xử lý ở tầng transport nếu muốn biến đổi; Subscription publisher errors cần `SubscriptionExceptionResolver`. Dùng `extensions.code` ổn định cho client, còn message chỉ là mô tả dành cho developer.

Lỗi nghiệp vụ dự đoán được có thể được mô hình hóa thành typed payload. Lỗi hạ tầng, authorization và lỗi bất thường nên đi qua top-level errors với thông tin được kiểm soát. Kết hợp error catalog, retry policy, correlation ID và contract tests giúp API tiến hóa mà không buộc client phụ thuộc vào implementation nội bộ.

## Tài liệu tham khảo

- [Spring for GraphQL — Request Execution and Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers and @GraphQlExceptionHandler](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQL — Response Format](https://graphql.org/learn/response/)
- [GraphQL — Error Handling](https://graphql.org/learn/error-handling/)
- [GraphQL Specification — Response](https://spec.graphql.org/September2026/#sec-Response)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
