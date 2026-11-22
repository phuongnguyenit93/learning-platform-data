# @GraphQlExceptionHandler

Trong Spring for GraphQL, exception có thể phát sinh khi resolver gọi service, truy vấn repository hoặc thực hiện quy tắc nghiệp vụ. Nếu để exception đi thẳng ra ngoài, client có thể nhận thông báo lỗi không nhất quán và server có nguy cơ tiết lộ chi tiết nội bộ. **@GraphQlExceptionHandler** cung cấp cách ánh xạ exception phát sinh trong quá trình thực thi field thành **GraphQLError** có cấu trúc.

Handler có thể được đặt ngay trong controller sở hữu resolver hoặc trong một **@ControllerAdvice** để áp dụng cho nhiều controller. Nhờ vậy, ứng dụng có thể chuẩn hóa error type, message, path, location và extensions theo contract GraphQL.

Bài này trình bày cách khai báo exception handler cục bộ và toàn cục, cách Spring chọn handler, cách xây dựng GraphQLError bằng GraphqlErrorBuilder, phân biệt lỗi thực thi với lỗi parse/validation/coercion, cách bảo vệ thông tin nhạy cảm, ảnh hưởng của nullability và kiểm thử bằng GraphQlTester.

## 1. @GraphQlExceptionHandler giải quyết vấn đề gì?

Giả sử resolver tìm một quyển sách:

~~~java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

Nếu không tìm thấy sách, service ném **BookNotFoundException**. Ứng dụng cần chuyển tình huống đó thành lỗi GraphQL mà client có thể hiểu.

Không nên để mỗi resolver tự bắt exception và tự tạo response theo cách riêng. Cách đó làm logic xử lý lỗi bị lặp và dễ không nhất quán. Với **@GraphQlExceptionHandler**, ứng dụng tập trung việc chuyển exception thành GraphQLError tại một nơi.

Ví dụ, mọi BookNotFoundException có thể được chuyển thành:

~~~json
{
  "message": "Không tìm thấy sách",
  "path": ["book"],
  "extensions": {
    "classification": "NOT_FOUND",
    "code": "BOOK_NOT_FOUND"
  }
}
~~~

Client có thể đọc mã lỗi ổn định BOOK_NOT_FOUND để hiển thị thông báo hoặc xử lý trạng thái phù hợp.

## 2. Exception handler cục bộ trong @Controller

Có thể khai báo một method **@GraphQlExceptionHandler** ngay trong annotated controller. Handler cục bộ phù hợp khi cách xử lý exception chỉ có ý nghĩa với các resolver trong controller đó.

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

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.NOT_FOUND)
                .message("Không tìm thấy sách")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
~~~

Trong ví dụ:

- **@GraphQlExceptionHandler** đánh dấu method xử lý exception.
- **BookNotFoundException** là loại exception cần xử lý.
- **DataFetchingEnvironment** cung cấp thông tin field đang được resolve.
- **GraphqlErrorBuilder.newError(environment)** tạo error gắn với execution environment hiện tại.
- **ErrorType.NOT_FOUND** phân loại lỗi theo nhóm công khai.
- **message** là thông báo an toàn dành cho client.
- **extensions** chứa mã lỗi ổn định do ứng dụng định nghĩa.

Khi bookService.findById ném BookNotFoundException, Spring tìm handler phù hợp và chuyển GraphQLError trả về cho GraphQL execution.

### Khi nào dùng handler cục bộ?

Handler cục bộ hữu ích khi:

- Exception chỉ xuất hiện trong một nhóm resolver.
- Cùng một exception class có cách biểu diễn khác nhau theo ngữ cảnh controller.
- Controller cần bổ sung thông tin field-specific vào error.
- Muốn đặt gần resolver để người đọc hiểu rõ mối quan hệ giữa use case và lỗi.

Nếu nhiều controller cần cùng một quy tắc xử lý, nên cân nhắc handler toàn cục.

## 3. Exception handler toàn cục bằng @ControllerAdvice

**@ControllerAdvice** cho phép đặt các method **@GraphQlExceptionHandler** trong một component dùng chung cho nhiều annotated controller.

Ví dụ:

~~~java
@ControllerAdvice
public class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.NOT_FOUND)
                .message("Không tìm thấy sách")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(
            AccessDeniedException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.FORBIDDEN)
                .message("Bạn không có quyền thực hiện thao tác này")
                .extensions(Map.of("code", "FORBIDDEN"))
                .build();
    }
}
~~~

Spring phát hiện **@ControllerAdvice** như một thành phần xử lý chung cho annotated controllers. Khi một exception phù hợp được ném ra trong quá trình resolve field, framework có thể tìm handler toàn cục tương ứng.

### Chọn phạm vi áp dụng

Nếu ứng dụng có nhiều GraphQL controller hoặc nhiều module nghiệp vụ, có thể giới hạn phạm vi của @ControllerAdvice bằng các thuộc tính chọn controller của Spring, chẳng hạn package hoặc kiểu controller. Điều này giúp tránh áp dụng một quy tắc lỗi cho những controller không thuộc phạm vi mong muốn.

Handler toàn cục phù hợp với các lỗi có semantics chung:

- Tài nguyên không tồn tại.
- Người dùng không đủ quyền.
- Dữ liệu đầu vào không hợp lệ ở tầng nghiệp vụ.
- Lỗi domain đã được chuẩn hóa.

Không nên gom mọi exception vào một handler toàn cục duy nhất rồi trả nguyên exception.getMessage() cho client.

## 4. Local handler và global handler

Hai cách khai báo có phạm vi khác nhau:

| Tiêu chí | Trong @Controller | Trong @ControllerAdvice |
|---|---|---|
| Phạm vi | Controller chứa handler | Các controller thuộc phạm vi advice |
| Dùng khi | Quy tắc đặc thù một controller | Quy tắc dùng chung |
| Tổ chức code | Gần resolver | Tập trung ở lớp advice |
| Tùy biến theo use case | Thuận tiện | Có thể dùng exception type hoặc metadata |
| Tái sử dụng | Thấp hơn | Cao hơn |

Khi cùng có handler cục bộ và toàn cục, handler cục bộ được ưu tiên cho controller sở hữu nó; handler toàn cục là nơi xử lý các trường hợp chung. Nếu cần quy tắc chi tiết hơn, hãy thiết kế exception type rõ ràng và phạm vi advice phù hợp thay vì dựa vào thứ tự ngẫu nhiên.

## 5. Spring chọn exception handler như thế nào?

Method handler cần khai báo loại exception mà nó xử lý. Spring tìm handler có thể nhận exception được ném ra, dựa trên kiểu exception và phạm vi handler.

Ví dụ:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleBookNotFound(
        BookNotFoundException exception,
        DataFetchingEnvironment environment) {
    // ...
}
~~~

Method trên khai báo rõ loại BookNotFoundException. Một handler có thể nhận kiểu cha như RuntimeException hoặc Exception, nhưng handler quá tổng quát dễ che mất ý nghĩa của lỗi cụ thể.

Nên ưu tiên:

- Exception domain cụ thể cho các trường hợp nghiệp vụ dự kiến.
- Exception security phù hợp cho authorization.
- Handler riêng cho các lỗi cần mã và message khác nhau.
- Một handler cuối cùng cho lỗi không dự kiến, với message chung và log nội bộ.

Không nên tạo nhiều handler có chữ ký mơ hồ cùng có thể xử lý một exception mà không hiểu quy tắc ưu tiên của framework. Khi có exception hierarchy, hãy dùng kiểu cụ thể và tổ chức handler dễ dự đoán.

## 6. Xây dựng GraphQLError bằng GraphqlErrorBuilder

**GraphQLError** là cấu trúc lỗi của GraphQL. Response GraphQL có thể chứa data và errors cùng lúc.

Một error thường có các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| message | Thông báo lỗi |
| locations | Vị trí field trong GraphQL document nếu có |
| path | Đường dẫn tới field phát sinh lỗi trong response |
| extensions | Metadata bổ sung như error code hoặc classification |

Spring for GraphQL dùng GraphQL Java, vì vậy có thể tạo error bằng **GraphqlErrorBuilder**.

~~~java
return GraphqlErrorBuilder.newError(environment)
        .errorType(ErrorType.NOT_FOUND)
        .message("Không tìm thấy sách")
        .extensions(Map.of(
                "code", "BOOK_NOT_FOUND",
                "resource", "Book"))
        .build();
~~~

newError(environment) giúp gắn thông tin vị trí và path theo field đang được resolve. Đây là điều quan trọng khi cùng một resolver được gọi nhiều lần trong list hoặc nested field.

### Error type

Spring for GraphQL cung cấp các nhóm lỗi thông dụng qua **org.springframework.graphql.execution.ErrorType**, ví dụ:

| ErrorType | Ý nghĩa thường dùng |
|---|---|
| BAD_REQUEST | Request hoặc dữ liệu đầu vào không hợp lệ |
| UNAUTHORIZED | Chưa xác thực hoặc không có credential phù hợp |
| FORBIDDEN | Đã xác thực nhưng không được phép thực hiện |
| NOT_FOUND | Không tìm thấy tài nguyên |
| INTERNAL_ERROR | Lỗi hệ thống không dự kiến |

Error type là phân loại của GraphQL error. Nó không tự quyết định HTTP status code của toàn bộ response. GraphQL over HTTP có quy tắc transport riêng; một operation có thể trả HTTP 200 nhưng trong body có errors.

## 7. Dùng extensions để tạo error contract ổn định

Không nên buộc client phân tích message để xác định loại lỗi. Message có thể thay đổi theo ngôn ngữ hoặc cách diễn đạt.

Hãy cung cấp mã lỗi ổn định trong extensions:

~~~java
return GraphqlErrorBuilder.newError(environment)
        .errorType(ErrorType.BAD_REQUEST)
        .message("Tiêu đề sách không được để trống")
        .extensions(Map.of(
                "code", "BOOK_TITLE_REQUIRED",
                "field", "title"))
        .build();
~~~

Response:

~~~json
{
  "data": {
    "createBook": null
  },
  "errors": [
    {
      "message": "Tiêu đề sách không được để trống",
      "path": ["createBook"],
      "extensions": {
        "classification": "BAD_REQUEST",
        "code": "BOOK_TITLE_REQUIRED",
        "field": "title"
      }
    }
  ]
}
~~~

Các key trong extensions là contract do ứng dụng thiết kế. Nên thống nhất tên key, kiểu dữ liệu và mã lỗi giữa các controller để client có thể xử lý nhất quán.

Có thể dùng enum nội bộ cho error code để tránh typo:

~~~java
public enum ApiErrorCode {
    BOOK_NOT_FOUND,
    BOOK_TITLE_REQUIRED,
    FORBIDDEN,
    INTERNAL_ERROR
}
~~~

Khi đưa ra GraphQL response, chuyển enum thành chuỗi có tính ổn định. Không dùng tên class exception Java làm mã lỗi công khai vì refactor code nội bộ có thể làm thay đổi API.

## 8. Path và location của lỗi

GraphQL error có thể chỉ ra:

- **path**: vị trí field trong response data.
- **locations**: vị trí field trong GraphQL document.

Ví dụ client query:

~~~graphql
query {
  books {
    id
    title
    author {
      name
    }
  }
}
~~~

Nếu resolve author của phần tử thứ hai gặp lỗi, path có thể có dạng:

~~~json
{
  "path": ["books", 1, "author"]
}
~~~

Path giúp client xác định field cụ thể bị lỗi, kể cả khi resolver được gọi cho nhiều object trong list.

Khi tạo error bằng GraphqlErrorBuilder.newError(environment), builder có thể lấy path và source location từ DataFetchingEnvironment. Đây là cách thuận tiện khi exception phát sinh trong một field cụ thể.

Đối với lỗi xảy ra trước khi DataFetcher chạy, chẳng hạn document parse hoặc schema validation, path có thể không tồn tại vì chưa có field execution cụ thể.

## 9. Phân biệt execution exception với parse, validation và coercion errors

**@GraphQlExceptionHandler** chủ yếu xử lý exception phát sinh khi DataFetcher/resolver đang thực thi. Không phải mọi lỗi GraphQL đều đi qua annotated exception handler.

| Nhóm lỗi | Ví dụ | Có đi qua @GraphQlExceptionHandler không? |
|---|---|---|
| Resolver/service exception | BookNotFoundException từ service | Có, nếu exception được ném ra trong field execution |
| Lỗi domain từ repository/service | Trạng thái không cho phép cập nhật | Có thể, nếu exception thoát ra từ resolver |
| Syntax error | Thiếu dấu ngoặc trong document | Không, xảy ra khi parse document |
| Schema validation error | Field không tồn tại trong type | Không, xảy ra trước resolver |
| Variable coercion error | Truyền String vào biến Int! | Không, thường bị từ chối trước field execution |
| Transport error | Body HTTP sai định dạng hoặc không đọc được | Không nhất thiết đi qua GraphQL exception handler |

Ví dụ lỗi parse:

~~~graphql
query {
  book(id: "book-01"
}
~~~

GraphQL parser không thể tạo operation hợp lệ, vì vậy controller book chưa được gọi.

Ví dụ lỗi validation:

~~~graphql
query {
  book(id: "book-01") {
    unknownField
  }
}
~~~

Nếu unknownField không có trong schema, GraphQL validation từ chối operation trước khi resolver thực thi.

Do đó, không nên dựa vào @GraphQlExceptionHandler để tùy biến tất cả lỗi cú pháp hoặc schema validation. Các lỗi đó thuộc giai đoạn GraphQL parse/validation và cần cơ chế xử lý tương ứng ở execution/transport layer.

## 10. Phân biệt GraphQL errors với payload userErrors

Một mutation có thể chọn trả lỗi nghiệp vụ trong payload:

~~~graphql
type UserError {
  code: String!
  message: String!
  field: [String!]!
}

type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
}

type Mutation {
  createBook(input: CreateBookInput!): CreateBookPayload!
}
~~~

Hai cách biểu diễn phục vụ mục đích khác nhau:

| Payload userErrors | GraphQL top-level errors |
|---|---|
| Lỗi nghiệp vụ dự kiến và client có thể xử lý như kết quả | Lỗi trong quá trình GraphQL execution hoặc operation |
| Nằm trong data.createBook.userErrors | Nằm ở mảng errors của response |
| Resolver vẫn trả payload bình thường | Field có thể nhận null và lỗi được ghi nhận |
| Phù hợp validation/domain outcome của mutation | Phù hợp exception không được biểu diễn như kết quả nghiệp vụ |

Ví dụ, tên sách đã được sử dụng có thể là userError nếu contract mutation thiết kế như vậy. Một database connection failure hoặc bug ngoài dự kiến nên đi qua GraphQL error handling, không nên biến thành userError giả.

@GraphQlExceptionHandler có thể chuyển exception thành top-level GraphQLError. Nó không tự tạo hoặc điền field userErrors trong payload. Nếu API muốn validation errors nằm trong payload, service/controller cần chủ động trả payload theo contract.

## 11. Bảo vệ thông tin nhạy cảm khi ánh xạ exception

Không nên trả nguyên message của exception cho client:

~~~java
@GraphQlExceptionHandler
public GraphQLError handle(Exception exception,
                           DataFetchingEnvironment environment) {
    return GraphqlErrorBuilder.newError(environment)
            .message(exception.getMessage())
            .build();
}
~~~

Đoạn code trên có thể tiết lộ:

- SQL hoặc tên bảng/cột.
- Đường dẫn file và cấu trúc thư mục nội bộ.
- Hostname, địa chỉ dịch vụ hoặc thông tin hạ tầng.
- Token, credential hoặc dữ liệu người dùng.
- Stack trace và chi tiết triển khai.

Nên trả message công khai an toàn, còn exception chi tiết được ghi log ở server:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleUnexpected(
        RuntimeException exception,
        DataFetchingEnvironment environment) {

    log.error("Unexpected GraphQL resolver error", exception);

    return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.INTERNAL_ERROR)
            .message("Đã xảy ra lỗi khi xử lý yêu cầu")
            .extensions(Map.of("code", "INTERNAL_ERROR"))
            .build();
}
~~~

Trong production, cần tránh log credential hoặc toàn bộ input nhạy cảm. Nên bổ sung correlation ID/trace ID để liên kết log mà không cần đưa stack trace vào response.

## 12. Không nên bắt mọi exception thành cùng một loại lỗi

Một handler cho Exception hoặc Throwable có thể làm lớp dự phòng cho lỗi không dự kiến, nhưng không nên dùng nó để thay thế các handler domain cụ thể.

Ví dụ:

- BookNotFoundException → NOT_FOUND.
- AccessDeniedException → FORBIDDEN.
- Lỗi validation nghiệp vụ đã nhận diện → BAD_REQUEST.
- Lỗi không dự kiến → INTERNAL_ERROR.

Nếu tất cả đều trả BAD_REQUEST, client sẽ hiểu sai lỗi hệ thống thành lỗi input. Nếu tất cả đều trả INTERNAL_ERROR, client không thể phân biệt tài nguyên không tồn tại với lỗi hạ tầng.

Nên ánh xạ theo semantics của lỗi, không chỉ theo tên package hoặc lớp exception.

### Đừng che giấu lỗi gốc

Khi bắt exception để đổi sang domain exception, giữ nguyên cause để log và điều tra:

~~~java
throw new BookPersistenceException(
        "Không thể lưu sách",
        originalException);
~~~

Handler công khai chỉ trả message và code an toàn. Cause đầy đủ vẫn được giữ ở server log.

## 13. Null propagation khi field resolver phát sinh exception

GraphQL response phụ thuộc nullability trong schema. Nếu field resolver ném exception và exception được chuyển thành GraphQLError, field bị lỗi được xem như không resolve được.

Schema:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  author: Author!
}
~~~

Nếu Book.author là non-null nhưng resolver author phát sinh lỗi, GraphQL không thể đặt null cho field này mà vẫn giữ contract. Null có thể lan lên object Book, rồi tiếp tục lan theo các field cha non-null.

Nếu author nullable:

~~~graphql
type Book {
  id: ID!
  author: Author
}
~~~

GraphQL có thể giữ Book và chỉ đặt author thành null, đồng thời thêm error vào response.

Ví dụ response có partial data:

~~~json
{
  "data": {
    "book": {
      "id": "book-01",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Không tìm thấy tác giả",
      "path": ["book", "author"],
      "extensions": {
        "code": "AUTHOR_NOT_FOUND"
      }
    }
  ]
}
~~~

Khi thiết kế schema, cần chọn nullability dựa trên khả năng lỗi và semantics domain. Exception handler không thể vô hiệu hóa quy tắc non-null propagation của GraphQL.

## 14. Xử lý lỗi bảo mật

Một số exception liên quan đến security có thể phát sinh khi resolver gọi service hoặc method security.

Ví dụ:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleAccessDenied(
        AccessDeniedException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.FORBIDDEN)
            .message("Bạn không có quyền thực hiện thao tác này")
            .extensions(Map.of("code", "FORBIDDEN"))
            .build();
}
~~~

Không phải mọi request chưa xác thực đều đi qua handler này. Security filter có thể từ chối request trước khi GraphQL execution bắt đầu; field authorization cũng có thể được xử lý ở các tầng khác.

Hãy phân biệt:

- **UNAUTHORIZED**: cần xác thực hoặc credential không hợp lệ.
- **FORBIDDEN**: principal đã xác thực nhưng không có quyền.

Thông báo không nên tiết lộ resource có tồn tại hay không nếu điều đó làm lộ dữ liệu. Với một số use case, trả cùng một thông báo cho cả not found và forbidden là quyết định bảo mật có chủ đích.

## 15. Kiểm thử @GraphQlExceptionHandler bằng GraphQlTester

GraphQlTester có thể kiểm tra GraphQL response khi resolver ném exception và handler chuyển nó thành GraphQLError.

Ví dụ:

~~~java
@SpringBootTest
class BookExceptionHandlerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldReturnNotFoundGraphQlError() {
        graphQlTester.document("""
                query {
                    book(id: "missing-book") {
                        id
                        title
                    }
                }
                """)
            .execute()
            .errors()
            .expect()
            .message("Không tìm thấy sách")
            .verify();
    }
}
~~~

Nên kiểm thử thêm:

1. Exception domain cụ thể được ánh xạ đúng error type.
2. Handler cục bộ được áp dụng cho controller tương ứng.
3. Handler toàn cục xử lý exception ở nhiều controller.
4. Error path trỏ đúng field đang thực thi.
5. Error location được giữ khi có DataFetchingEnvironment.
6. Extensions chứa error code ổn định.
7. AccessDeniedException trả lỗi phù hợp với chính sách.
8. Exception không dự kiến trả message chung, không lộ stack trace.
9. Partial data và null propagation phù hợp schema.
10. Lỗi parse/validation không bị nhầm là exception từ resolver.

Nếu cần xác minh path và extensions, có thể kiểm tra danh sách errors trong response:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "missing-book") {
                id
            }
        }
        """)
    .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).anySatisfy(error -> {
        assertThat(error.getPath()).containsExactly("book");
        assertThat(error.getExtensions())
                .containsEntry("code", "BOOK_NOT_FOUND");
    });
});
~~~

Tên API kiểm thử cụ thể có thể thay đổi theo phiên bản Spring for GraphQL; hãy dùng GraphQlTester của dependency đang có trong ứng dụng. Điều quan trọng là kiểm tra cả message, path, extensions và data.

## 16. Những lỗi thường gặp khi dùng @GraphQlExceptionHandler

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Handler không được gọi | Exception xảy ra trước resolver hoặc không thuộc phạm vi handler | Xác định giai đoạn phát sinh lỗi |
| Local handler không xử lý controller khác | Handler chỉ nằm trong controller hiện tại | Dùng @ControllerAdvice nếu cần phạm vi chung |
| Error path bị thiếu | Tạo GraphQLError không gắn execution environment | Dùng GraphqlErrorBuilder.newError(environment) |
| Client nhận message nội bộ | Trả exception.getMessage() trực tiếp | Dùng message công khai và log chi tiết ở server |
| Mọi lỗi đều thành INTERNAL_ERROR | Handler quá tổng quát | Tạo mapping cho exception domain cụ thể |
| Validation syntax không đi qua handler | Parse/validation xảy ra trước DataFetcher | Dùng cơ chế xử lý lỗi ở đúng tầng |
| Data biến mất nhiều hơn dự kiến | Field non-null gây null propagation | Xem lại nullability và semantics |
| Client phụ thuộc message | Không có error code ổn định | Đưa mã vào extensions |
| HTTP status không như ErrorType | Nhầm GraphQL error classification với HTTP status | Xử lý transport status theo quy tắc GraphQL over HTTP |
| Security error tiết lộ resource | Message phân biệt quá chi tiết | Chuẩn hóa thông báo theo threat model |

## 17. Quy trình triển khai @GraphQlExceptionHandler

Khi cần ánh xạ exception thành GraphQL error:

1. Xác định exception phát sinh trong resolver, service hay trước GraphQL execution.
2. Tạo exception type cụ thể cho lỗi domain cần xử lý.
3. Chọn handler cục bộ trong @Controller hoặc handler chung trong @ControllerAdvice.
4. Khai báo kiểu exception mà method xử lý.
5. Nhận DataFetchingEnvironment nếu cần path và location.
6. Dùng GraphqlErrorBuilder để tạo GraphQLError.
7. Chọn ErrorType đúng semantics của lỗi.
8. Đặt message công khai an toàn và mã ổn định trong extensions.
9. Log exception gốc ở server với correlation ID phù hợp.
10. Kiểm tra nullability và partial data sau khi field phát sinh lỗi.
11. Viết GraphQlTester cho local/global handler, path, extensions và security.
12. Kiểm tra riêng lỗi parse, validation và variable coercion vì chúng không đi qua resolver exception handler.

@GraphQlExceptionHandler giúp Spring for GraphQL chuyển exception trong quá trình resolve field thành GraphQLError có cấu trúc. Handler cục bộ phù hợp với quy tắc riêng của controller; @ControllerAdvice phù hợp với quy tắc dùng chung. Khi xây dựng error, hãy giữ path/location, phân loại lỗi theo semantics, cung cấp mã ổn định trong extensions và bảo vệ chi tiết nội bộ. Đồng thời cần nhớ annotation này xử lý exception ở giai đoạn field execution; lỗi parse, validation và coercion thuộc các giai đoạn trước đó. Kiểm thử cả error response lẫn partial data sẽ giúp contract lỗi rõ ràng và nhất quán.
