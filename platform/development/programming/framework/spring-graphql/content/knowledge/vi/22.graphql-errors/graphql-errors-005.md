# GraphQlExceptionHandler

Trong Spring for GraphQL, **@GraphQlExceptionHandler** cho phép chuyển exception phát sinh khi thực thi GraphQL field thành một GraphQL error có cấu trúc và thông điệp phù hợp với client. Annotation này giúp controller xử lý lỗi nghiệp vụ như không tìm thấy resource, dữ liệu không hợp lệ hoặc không đủ quyền mà không phải tự tạo response JSON.

Exception handler có thể được khai báo ngay trong controller hoặc đặt tập trung trong `@ControllerAdvice`. Bài học trình bày cách đăng ký handler, chọn loại lỗi, giữ path và location của field, trả dữ liệu một phần, phân biệt execution error với request error, kết hợp `DataFetcherExceptionResolver` và kiểm thử bằng `GraphQlTester`.

## 1. Vì sao cần GraphQlExceptionHandler?

Giả sử schema có Query tìm sách:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

Service có thể ném exception khi không tìm thấy sách:

~~~java
public Book findById(String id) {
    return bookRepository.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

Nếu resolver không xử lý exception, GraphQL engine vẫn cần tạo response theo GraphQL response format. Client cần nhận một lỗi có ý nghĩa, ví dụ mã `BOOK_NOT_FOUND`, thay vì thông tin nội bộ như câu SQL, stack trace hoặc tên class Java.

Spring for GraphQL cung cấp `@GraphQlExceptionHandler` để ánh xạ exception thành `GraphQLError`:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception) {

        return GraphqlErrorBuilder.newError()
                .message("Không tìm thấy sách")
                .errorType(ErrorType.NOT_FOUND)
                .build();
    }
}
~~~

Khi `findById` ném `BookNotFoundException`, Spring tìm handler tương ứng và dùng GraphQLError mà handler trả về để ghi lỗi vào response GraphQL.

`@GraphQlExceptionHandler` xử lý exception trong quá trình thực thi field. Nó không thay thế việc kiểm tra cú pháp operation hoặc validation schema trước khi resolver chạy.

## 2. GraphQL error khác HTTP error như thế nào?

GraphQL thường trả kết quả của operation trong response body. Một response có thể chứa cả `data` và `errors`.

Ví dụ khi field `book` nullable và không tìm thấy resource:

~~~json
{
    "data": {
        "book": null
    },
    "errors": [
        {
            "message": "Không tìm thấy sách",
            "path": ["book"],
            "extensions": {
                "classification": "NOT_FOUND",
                "code": "BOOK_NOT_FOUND"
            }
        }
    ]
}
~~~

Điểm cần hiểu:

- `data` mô tả kết quả của các field thực thi được.
- `errors` mô tả lỗi phát sinh trong quá trình xử lý operation.
- `path` chỉ vị trí field gây lỗi trong response.
- `locations` có thể chỉ vị trí field trong GraphQL document.
- `extensions` chứa metadata bổ sung như mã lỗi hoặc classification.

Một GraphQL execution error không nhất thiết làm toàn bộ HTTP request thất bại. Với HTTP transport, server thường vẫn trả response GraphQL theo giao thức, còn trạng thái HTTP phụ thuộc loại lỗi và cấu hình transport.

Không nên xem mọi GraphQL error là HTTP 500. Lỗi nghiệp vụ như không tìm thấy resource hoặc không đủ quyền có thể được biểu diễn trong `errors` trong khi response vẫn là một GraphQL response hợp lệ.

## 3. Handler trong controller và @ControllerAdvice

Có hai vị trí phổ biến để khai báo `@GraphQlExceptionHandler`.

### Handler cục bộ trong controller

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .message("Không tìm thấy sách")
                .errorType(ErrorType.NOT_FOUND)
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
~~~

Handler được đặt trong controller phù hợp khi lỗi chỉ có ý nghĩa với các resolver của controller đó hoặc cách diễn giải lỗi phụ thuộc vào domain cụ thể.

### Handler dùng chung với @ControllerAdvice

Khi nhiều controller cần cùng một quy tắc xử lý, có thể đặt handler trong `@ControllerAdvice`:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.Map;

@ControllerAdvice
public class GraphQlGlobalExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .message("Không tìm thấy sách")
                .errorType(ErrorType.NOT_FOUND)
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
~~~

`@ControllerAdvice` giúp gom các quy tắc chung như validation error, access denied hoặc lỗi nghiệp vụ dùng ở nhiều resolver.

| Vị trí | Phạm vi phù hợp |
| --- | --- |
| `@Controller` | Lỗi đặc thù của một controller hoặc một nhóm resolver gần nhau. |
| `@ControllerAdvice` | Lỗi dùng chung giữa nhiều annotated controller. |

Nếu có cả handler cục bộ và handler dùng chung, hãy thiết kế phạm vi rõ ràng. Handler cục bộ phù hợp với lỗi chỉ controller đó hiểu; advice xử lý các lỗi chung chưa được xử lý tại controller.

## 4. Exception handler được chọn như thế nào?

Một handler cần khai báo kiểu exception mà nó xử lý qua tham số exception của method.

Ví dụ:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleNotFound(
        BookNotFoundException exception,
        DataFetchingEnvironment environment) {
    // ...
}
~~~

Spring tìm handler phù hợp với exception phát sinh trong quá trình gọi data fetcher. Nên dùng exception nghiệp vụ cụ thể để tránh một handler quá rộng vô tình bắt các lỗi không cùng ý nghĩa.

Ví dụ, không nên dùng một handler duy nhất cho mọi `RuntimeException` rồi trả về `NOT_FOUND`. Lỗi không tìm thấy sách, lỗi validation, lỗi quyền truy cập và lỗi database cần được phân loại khác nhau.

Có thể tổ chức exception theo domain:

~~~java
public class BookNotFoundException extends RuntimeException {
    public BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}

public class InvalidBookInputException extends RuntimeException {
    public InvalidBookInputException(String message) {
        super(message);
    }
}
~~~

Handler dùng loại exception để xác định mã lỗi công khai. Không nhất thiết phải gửi nguyên `exception.getMessage()` cho client, vì message nội bộ có thể chứa ID, truy vấn hoặc chi tiết không nên tiết lộ.

## 5. Tạo GraphQLError với ErrorType

Spring for GraphQL cung cấp `ErrorType` để phân loại các lỗi phổ biến.

Một số giá trị thường dùng:

| ErrorType | Ý nghĩa |
| --- | --- |
| `BAD_REQUEST` | Input hoặc yêu cầu không hợp lệ trong ngữ cảnh thực thi. |
| `UNAUTHORIZED` | Chưa được xác thực hoặc không có thông tin xác thực phù hợp. |
| `FORBIDDEN` | Đã xác thực nhưng không được phép thực hiện thao tác. |
| `NOT_FOUND` | Không tìm thấy resource cần thiết. |
| `INTERNAL_ERROR` | Lỗi nội bộ không nên tiết lộ chi tiết cho client. |

Đây là các classification chuẩn thường dùng của Spring for GraphQL. Với trường hợp chi tiết hơn như xung đột phiên bản, dịch vụ phụ thuộc tạm thời không khả dụng hoặc timeout, hãy dùng `extensions.code` để công bố mã nghiệp vụ ổn định; chọn `ErrorType` theo nhóm tổng quát phù hợp với chính sách API.

Ví dụ xử lý input không hợp lệ:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleInvalidInput(
        InvalidBookInputException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
            .message("Dữ liệu sách không hợp lệ")
            .errorType(ErrorType.BAD_REQUEST)
            .extensions(Map.of("code", "INVALID_BOOK_INPUT"))
            .build();
}
~~~

`ErrorType` cung cấp classification nhất quán cho lỗi. Client có thể dựa vào mã ổn định trong `extensions` để hiển thị thông báo hoặc quyết định hành động tiếp theo.

Không nên dùng `INTERNAL_ERROR` cho mọi lỗi nghiệp vụ. Phân loại đúng giúp theo dõi lỗi và xử lý phía client dễ dàng hơn.

## 6. Bổ sung mã lỗi qua extensions

`GraphQLError` có trường `extensions` để chứa metadata bổ sung. Đây là nơi thích hợp cho mã lỗi ổn định mà client có thể xử lý bằng code.

Ví dụ:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleBookConflict(
        BookConflictException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
            .message("Sách đã được cập nhật bởi một thao tác khác")
            .errorType(ErrorType.BAD_REQUEST)
            .extensions(Map.of(
                    "code", "BOOK_VERSION_CONFLICT",
                    "retryable", true
            ))
            .build();
}
~~~

Response có thể chứa:

~~~json
{
    "errors": [
        {
            "message": "Sách đã được cập nhật bởi một thao tác khác",
            "path": ["updateBook"],
            "extensions": {
                "classification": "BAD_REQUEST",
                "code": "BOOK_VERSION_CONFLICT",
                "retryable": true
            }
        }
    ]
}
~~~

Quy ước extension nên ổn định và được tài liệu hóa. Không đưa các giá trị tùy tiện như stack trace, SQL, connection string, token hoặc thông tin xác thực vào extensions.

Nên dùng mã lỗi dạng hằng số hoặc enum ở server để tránh sai chính tả và giúp client xử lý nhất quán.

## 7. Giữ path và location bằng DataFetchingEnvironment

Khi tạo GraphQLError, có thể truyền `DataFetchingEnvironment` cho `GraphqlErrorBuilder.newError(environment)`:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleNotFound(
        BookNotFoundException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
            .message("Không tìm thấy sách")
            .errorType(ErrorType.NOT_FOUND)
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
}
~~~

Builder được tạo từ environment có thông tin của field đang được thực thi, bao gồm path và source location phù hợp. Điều này đặc biệt hữu ích khi cùng một exception type có thể xảy ra ở nhiều field hoặc trong một selection set lồng nhau.

Ví dụ query:

~~~graphql
query {
    books {
        id
        publisher {
            name
        }
    }
}
~~~

Nếu lỗi xảy ra ở `publisher.name` của phần tử thứ hai, path có thể mô tả vị trí tương tự:

~~~json
{
    "path": ["books", 1, "publisher", "name"]
}
~~~

Client có thể dùng path để xác định field nào không hoàn thành được. Nếu tự tạo error bằng `GraphqlErrorBuilder.newError()` không có environment, path/location có thể không được gắn như mong muốn. Khi xử lý lỗi của một DataFetcher cụ thể, ưu tiên builder nhận environment.

## 8. Partial data và null propagation

GraphQL có thể trả dữ liệu thành công của một số field cùng lỗi ở field khác.

Ví dụ schema:

~~~graphql
type Query {
    book(id: ID!): Book
    serviceStatus: String!
}
~~~

Client query:

~~~graphql
query {
    book(id: "missing") {
        id
        title
    }
    serviceStatus
}
~~~

Nếu `book` là nullable, lỗi tại field này có thể tạo response:

~~~json
{
    "data": {
        "book": null,
        "serviceStatus": "UP"
    },
    "errors": [
        {
            "message": "Không tìm thấy sách",
            "path": ["book"]
        }
    ]
}
~~~

Field `serviceStatus` vẫn có thể trả kết quả.

Nếu schema khai báo `book: Book!`, resolver không thể hoàn thành field bằng null. GraphQL áp dụng quy tắc non-null propagation: null lan lên parent gần nhất cho phép null. Nếu parent cũng non-null, quá trình tiếp tục lan lên trên. Trong trường hợp lỗi lan tới root `data`, toàn bộ `data` có thể là null.

Vì vậy, nullability trong SDL là một phần của hợp đồng lỗi. Hãy chọn nullable/non-null dựa trên việc client có thể tiếp tục sử dụng phần dữ liệu còn lại hay không, thay vì chỉ dựa vào mong muốn response luôn có dữ liệu.

## 9. Phân biệt execution error và request error

`@GraphQlExceptionHandler` tập trung vào exception phát sinh trong quá trình thực thi data fetcher. Một số lỗi xảy ra trước khi resolver được gọi.

| Loại lỗi | Thời điểm | Ví dụ | Handler resolver có xử lý không? |
| --- | --- | --- | --- |
| Parse error | Đọc GraphQL document | Thiếu dấu ngoặc, cú pháp sai | Không |
| Validation error | Kiểm tra document với schema | Gọi field không tồn tại | Không |
| Input coercion error | Chuẩn hóa variables/arguments | Thiếu input field non-null, enum sai | Không |
| Execution error | Chạy resolver/data fetcher | Service ném `BookNotFoundException` | Có |
| Binding/validation trong resolver invocation | Chuyển argument vào method hoặc kiểm tra dữ liệu | DTO không bind được hoặc validation phát sinh exception | Tùy điểm phát sinh và cơ chế xử lý được cấu hình |

Ví dụ parse error:

~~~graphql
query {
    book(id: "1" {
        id
    }
}
~~~

GraphQL không thể parse document nên không có resolver `book` nào được gọi. Handler của controller không thể sửa cú pháp operation.

Ví dụ validation error: schema không có field `unknownBooks`, nhưng client gọi field này. Đây là lỗi kiểm tra document trước execution.

Nếu client gửi `ID!` bị thiếu hoặc enum không hợp lệ, GraphQL có thể từ chối request trong giai đoạn input coercion. Đây cũng không phải exception nghiệp vụ trong resolver.

Cần chọn cơ chế phù hợp cho từng giai đoạn: client sửa operation/input, server sửa schema hoặc cấu hình, còn `@GraphQlExceptionHandler` xử lý exception trong quá trình thực thi field.

## 10. Phân biệt @GraphQlExceptionHandler với @ExceptionHandler

Spring MVC có `@ExceptionHandler` để xử lý exception trong luồng request của controller HTTP. Spring for GraphQL có `@GraphQlExceptionHandler` cho exception trong quá trình thực thi GraphQL data fetcher.

| Annotation | Phạm vi |
| --- | --- |
| `@ExceptionHandler` | Xử lý exception trong cơ chế Spring MVC/WebFlux controller HTTP. |
| `@GraphQlExceptionHandler` | Chuyển exception của GraphQL data fetcher thành GraphQL error. |

GraphQL controller thường không trực tiếp tạo HTTP response như REST controller. Một GraphQL operation có thể có nhiều field và partial data, vì vậy exception handler cần tạo `GraphQLError` theo GraphQL response semantics.

Không dùng `@ExceptionHandler` thay cho `@GraphQlExceptionHandler` khi mục tiêu là xử lý exception phát sinh từ resolver GraphQL.

## 11. Khi nào cần DataFetcherExceptionResolver?

`@GraphQlExceptionHandler` thuận tiện cho các annotated controller. Khi cần xử lý exception tập trung ở tầng GraphQL execution hoặc cần tích hợp logic resolver tổng quát, có thể triển khai `DataFetcherExceptionResolver`.

Ví dụ adapter:

~~~java
@Component
public class BookDataFetcherExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .message("Không tìm thấy sách")
                    .errorType(ErrorType.NOT_FOUND)
                    .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                    .build();
        }

        return null;
    }
}
~~~

Resolver trả về GraphQLError khi nhận biết exception. Trả `null` có nghĩa resolver này không xử lý exception đó, để cơ chế resolver tiếp theo có cơ hội xử lý.

Nên chọn một chiến lược chính cho từng nhóm lỗi:

- Dùng `@GraphQlExceptionHandler` khi xử lý exception gắn với annotated controller.
- Dùng `DataFetcherExceptionResolver` khi cần quy tắc tập trung ở tầng execution, bao gồm các data fetcher không phải annotated controller.
- Tránh triển khai cùng một mapping ở nhiều nơi nếu không có quy tắc ưu tiên rõ ràng.

Không nên viết resolver tùy chỉnh chỉ để đổi message đơn giản nếu annotation đã đáp ứng nhu cầu.

## 12. Xử lý lỗi bảo mật và không để lộ thông tin nội bộ

Exception có thể chứa thông tin nhạy cảm:

- SQL statement hoặc tên bảng.
- Đường dẫn file nội bộ.
- Tên host, port hoặc connection string.
- Token, credential hoặc dữ liệu cá nhân.
- Stack trace và chi tiết cấu hình.
- ID nội bộ mà client không được phép biết.

Không trả trực tiếp `exception.getMessage()` cho mọi exception. Thay vào đó, dùng thông điệp an toàn và mã lỗi công khai:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleUnexpectedError(
        RuntimeException exception,
        DataFetchingEnvironment environment) {

    log.error(
            "Unexpected GraphQL error at {}",
            environment.getExecutionStepInfo().getPath(),
            exception
    );

    return GraphqlErrorBuilder.newError(environment)
            .message("Đã xảy ra lỗi khi xử lý yêu cầu")
            .errorType(ErrorType.INTERNAL_ERROR)
            .extensions(Map.of("code", "INTERNAL_ERROR"))
            .build();
}
~~~

Ví dụ này minh họa nguyên tắc che giấu chi tiết nội bộ. Trong hệ thống thực tế, hãy cân nhắc thứ tự và phạm vi handler để một handler rộng cho `RuntimeException` không che mất các exception nghiệp vụ đã được phân loại.

Với lỗi quyền truy cập, không tiết lộ resource có tồn tại hay không nếu chính sách bảo mật yêu cầu che giấu sự tồn tại đó. Dùng cùng một thông điệp hoặc mã lỗi cho các trường hợp cần thiết theo threat model của ứng dụng.

## 13. Kết hợp Spring Security với GraphQlExceptionHandler

Một resolver có thể gọi service và nhận `AccessDeniedException` nếu người dùng không có quyền.

Ví dụ:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleAccessDenied(
        AccessDeniedException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
            .message("Bạn không có quyền thực hiện thao tác này")
            .errorType(ErrorType.FORBIDDEN)
            .extensions(Map.of("code", "ACCESS_DENIED"))
            .build();
}
~~~

Tuy nhiên, không phải mọi lỗi xác thực hoặc authorization đều phát sinh trong resolver. Một số request có thể bị Spring Security filter từ chối trước khi GraphQL engine nhận operation. `@GraphQlExceptionHandler` không thay thế cấu hình authentication/authorization ở transport layer.

Nên phân biệt:

- Authentication: xác định người dùng là ai.
- Authorization: xác định người dùng có được phép thực hiện hành động không.
- GraphQL error mapping: biểu diễn exception phát sinh trong execution thành lỗi theo hợp đồng GraphQL.

Không dùng exception handler để thay thế kiểm tra quyền ở service hoặc method security.

## 14. Kiểm thử GraphQlExceptionHandler bằng GraphQlTester

Nên kiểm thử handler qua GraphQL operation thực tế thay vì chỉ gọi method handler trực tiếp.

Ví dụ controller có resolver:

~~~java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

Global exception handler trả `NOT_FOUND` khi service ném `BookNotFoundException`.

Test:

~~~java
@Test
void mapsBookNotFoundToGraphQlError() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                book(id: "missing") {
                    id
                    title
                }
            }
            """)
        .execute();

    response.errors().satisfy(errors ->
            assertThat(errors).anySatisfy(error -> {
                assertThat(error.getMessage())
                        .isEqualTo("Không tìm thấy sách");
                assertThat(error.getPath())
                        .containsExactly("book");
                assertThat(error.getExtensions())
                        .containsEntry("code", "BOOK_NOT_FOUND");
            }));

    response.path("book").valueIsNull();
}
~~~

Ví dụ này giả định field `book` nullable trong SDL. Nếu field là non-null, cần kiểm tra null propagation ở parent/root theo schema thực tế.

Các trường hợp nên kiểm thử:

- Exception nghiệp vụ được ánh xạ đúng ErrorType.
- `extensions.code` có mã ổn định.
- Path chỉ đúng field gây lỗi.
- Partial data của field khác vẫn được giữ.
- Non-null propagation tuân theo SDL.
- Handler cục bộ chỉ xử lý lỗi thuộc controller đó.
- Handler trong `@ControllerAdvice` áp dụng cho nhiều controller.
- Exception không được handler nhận diện đi tới resolver tiếp theo hoặc cơ chế fallback.
- Response không chứa stack trace, SQL hoặc rejected value nhạy cảm.
- Parse/validation/coercion error không bị nhầm là execution exception.

Với test handler dùng chung, nên kiểm thử ít nhất một resolver ở mỗi controller hoặc một operation đại diện để xác nhận advice được phát hiện trong application context.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Handler không được gọi | Method không nằm trong controller/advice được Spring phát hiện hoặc exception không phát sinh trong execution. | Kiểm tra component scan, annotation và giai đoạn lỗi. |
| Handler không khớp exception | Tham số exception không tương thích với exception thực tế. | Dùng kiểu exception cụ thể và kiểm tra cause. |
| Client nhận lỗi chung chung | Không có handler phù hợp hoặc resolver fallback xử lý. | Đăng ký handler cho exception nghiệp vụ cần phân loại. |
| Path không có hoặc không đúng | Tạo GraphQLError mà không dùng execution environment. | Dùng `GraphqlErrorBuilder.newError(environment)`. |
| Mất partial data | Hiểu nhầm lỗi field làm hỏng toàn operation hoặc field cha non-null. | Kiểm tra nullability và null propagation. |
| Mọi lỗi đều thành NOT_FOUND | Handler bắt exception quá rộng. | Tách exception theo nghiệp vụ và ErrorType. |
| Lộ stack trace hoặc SQL | Trả nguyên exception message cho client. | Dùng message an toàn, log chi tiết ở server. |
| `@ExceptionHandler` không xử lý lỗi resolver | Dùng annotation của HTTP controller thay cho GraphQL handler. | Dùng `@GraphQlExceptionHandler` hoặc DataFetcherExceptionResolver. |
| Handler không bắt parse error | Parse/validation diễn ra trước data fetcher. | Sửa request/schema hoặc xử lý ở tầng request/transport phù hợp. |
| Lỗi quyền bị trả sai classification | Trộn authentication, authorization và business exception. | Phân biệt UNAUTHORIZED, FORBIDDEN và lỗi nghiệp vụ. |

## 16. Quy trình thiết kế exception handling

Khi bổ sung xử lý lỗi cho GraphQL API, có thể làm theo trình tự:

1. Xác định exception phát sinh ở request stage hay execution stage.
2. Tạo exception nghiệp vụ cụ thể cho các tình huống có ý nghĩa với client.
3. Chọn handler cục bộ hoặc `@ControllerAdvice` theo phạm vi sử dụng.
4. Chọn `ErrorType` phù hợp.
5. Định nghĩa mã lỗi ổn định trong `extensions`.
6. Dùng `DataFetchingEnvironment` khi cần giữ path/location.
7. Thiết kế message an toàn, không tiết lộ thông tin nội bộ.
8. Kiểm tra nullability của field và tác động của null propagation.
9. Dùng `DataFetcherExceptionResolver` nếu cần xử lý tập trung ở tầng execution.
10. Kiểm thử errors, path, extensions và partial data bằng `GraphQlTester`.
11. Kiểm thử riêng parse, validation và input coercion error.
12. Theo dõi log/metrics ở server bằng correlation ID phù hợp.

## 17. Những điểm cần ghi nhớ

- `@GraphQlExceptionHandler` chuyển exception phát sinh khi thực thi GraphQL data fetcher thành `GraphQLError`.
- Handler có thể nằm trong `@Controller` hoặc `@ControllerAdvice`.
- Dùng exception nghiệp vụ cụ thể để tránh phân loại sai lỗi.
- `ErrorType` cung cấp classification; `extensions` có thể chứa mã lỗi ổn định cho client.
- Dùng `GraphqlErrorBuilder.newError(environment)` để giữ path và location của field.
- GraphQL có thể trả `data` một phần cùng `errors`; nullability quyết định cách null lan truyền.
- Parse, validation và input coercion error xảy ra trước resolver nên không được xử lý như execution exception.
- `@GraphQlExceptionHandler` khác `@ExceptionHandler` của Spring MVC.
- `DataFetcherExceptionResolver` phù hợp khi cần xử lý lỗi tập trung ở tầng GraphQL execution.
- Không trả stack trace, SQL, token hoặc thông tin nội bộ trong message/extensions.
- Dùng `GraphQlTester` để kiểm tra ErrorType, path, extensions và partial data.

`@GraphQlExceptionHandler` giúp chuẩn hóa lỗi nghiệp vụ trong Spring for GraphQL theo đúng response semantics của GraphQL. Khi phân loại exception rõ ràng, giữ path của field, tôn trọng nullability và bảo vệ thông tin nội bộ, client có thể xử lý lỗi nhất quán mà vẫn sử dụng được phần dữ liệu hợp lệ của operation.

