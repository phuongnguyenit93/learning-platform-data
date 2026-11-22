# Mutation error response trong Spring for GraphQL

Khi một mutation không thể hoàn thành, GraphQL có thể trả lỗi ở cấp thực thi hoặc trả một kết quả nghiệp vụ có mô tả lỗi ngay trong `data`. Hai cách này phục vụ những tình huống khác nhau. Lỗi thực thi phù hợp với exception, lỗi hệ thống hoặc request không hợp lệ; kết quả nghiệp vụ có kiểu rõ ràng phù hợp với những trường hợp người dùng có thể sửa và gửi lại, chẳng hạn dữ liệu bị trùng hoặc đầu vào không vượt qua quy tắc nghiệp vụ.

Với Spring for GraphQL, resolver mutation thường được viết bằng `@MutationMapping`. Exception từ resolver có thể được ánh xạ thành `GraphQLError` bằng `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver`. Nếu muốn client xử lý lỗi nghiệp vụ như một phần kết quả bình thường, hãy thiết kế payload trong SDL và trả dữ liệu đó từ resolver.

## 1. GraphQL biểu diễn lỗi như thế nào?

Một GraphQL response có thể chứa `data`, `errors` hoặc cả hai. `errors` là danh sách các lỗi phát sinh trong quá trình xử lý operation. Mỗi lỗi có thể chứa:

- `message`: mô tả lỗi dành cho client.
- `locations`: vị trí trong GraphQL document nơi lỗi được phát hiện, nếu có.
- `path`: đường dẫn tới field trong response gây ra lỗi thực thi.
- `extensions`: metadata bổ sung do server cung cấp, ví dụ mã lỗi ổn định.

Ví dụ, client gọi mutation tạo sách nhưng không tìm thấy một tài nguyên liên quan:

```graphql
mutation {
    publishBook(id: "missing-book") {
        id
        title
    }
}
```

Nếu resolver ném exception và exception handler ánh xạ thành GraphQL error, response có thể có dạng:

```json
{
  "data": {
    "publishBook": null
  },
  "errors": [
    {
      "message": "Book not found",
      "path": ["publishBook"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
```

Đây là ví dụ minh họa cấu trúc. `locations`, `path` và nội dung `extensions` thực tế phụ thuộc vào vị trí lỗi và cách server tạo `GraphQLError`.

Một lỗi thực thi không nhất thiết làm toàn bộ `data` biến mất. GraphQL có thể trả một phần dữ liệu đã phân giải thành công, trong khi field bị lỗi nhận `null`. Nếu field đó có kiểu Non-null, `null` có thể lan truyền lên field cha nullable gần nhất theo quy tắc null propagation.

## 2. Phân biệt request error, execution error và business error

Không phải lỗi nào cũng nên được xử lý giống nhau:

| Loại lỗi | Xảy ra khi nào? | Resolver mutation có chạy không? | Cách phản hồi thường dùng |
|---|---|---|---|
| Request error | Document sai cú pháp, field không tồn tại, argument sai kiểu hoặc biến không thể coercion | Không | GraphQL trả `errors`; request không được thực thi. |
| Execution error | Resolver hoặc một field con ném exception, hoặc không thể tạo giá trị hợp lệ | Có thể đã chạy | GraphQL trả `errors`, `path` và phần `data` còn hợp lệ. |
| Business error dự kiến | Dữ liệu không đáp ứng quy tắc nghiệp vụ, ví dụ ISBN trùng hoặc trạng thái không cho phép | Có | Thường trả payload có `userErrors` hoặc kiểu kết quả cụ thể trong `data`. |

Ví dụ, nếu SDL khai báo `createBook(input: CreateBookInput!): Book!` nhưng client bỏ `input`, GraphQL có thể từ chối request trước khi gọi phương thức `@MutationMapping`. Đây là lỗi request. Nếu resolver đã chạy rồi service gặp lỗi kết nối database, đó là lỗi thực thi. Nếu ISBN đã được sử dụng và người dùng có thể nhập ISBN khác, đó là business error có thể biểu diễn thành payload.

Phân loại đúng giúp client biết khi nào cần sửa GraphQL document, khi nào cần hiển thị lỗi hệ thống và khi nào chỉ cần yêu cầu người dùng sửa dữ liệu.

## 3. Mutation và lỗi thực thi do exception

Xét schema:

```graphql
type Mutation {
    deleteBook(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

Resolver:

```java
@Controller
class BookMutationController {

    private final BookService bookService;

    BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    Book deleteBook(@Argument("id") String id) {
        return bookService.deleteById(id);
    }
}
```

Nếu `deleteById` ném `BookNotFoundException`, Spring for GraphQL cần chuyển exception đó thành một GraphQL error có thông tin phù hợp. Không nên để message mặc định hoặc exception nội bộ vô tình tiết lộ chi tiết triển khai cho client.

Trong ví dụ này `deleteBook` có kiểu nullable (`Book`), vì vậy khi resolver lỗi, response có thể giữ `data.deleteBook: null` cùng danh sách `errors`. Nếu đổi thành `Book!`, lỗi sẽ làm `null` lan truyền lên cấp cha nullable gần nhất; với field root mutation, điều đó có thể khiến toàn bộ `data` thành `null`. Nếu không tìm thấy sách là một trạng thái bình thường mà client cần xử lý, cân nhắc dùng payload nullable hoặc kết quả có kiểu thay vì cam kết một object luôn tồn tại.

## 4. Ánh xạ exception bằng `@GraphQlExceptionHandler`

Spring for GraphQL hỗ trợ `@GraphQlExceptionHandler` để xử lý exception từ các controller GraphQL. Có thể đặt handler trong `@ControllerAdvice` để dùng chung cho nhiều controller hoặc đặt trong controller nếu phạm vi xử lý chỉ thuộc controller đó.

Ví dụ định nghĩa exception:

```java
public class BookNotFoundException extends RuntimeException {

    public BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}
```

Handler chuyển exception thành `GraphQLError`:

```java
@ControllerAdvice
class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    GraphQLError handleBookNotFound(
            BookNotFoundException ex,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
    }
}
```

`GraphqlErrorBuilder.newError(environment)` giúp gắn thông tin thực thi như vị trí và đường dẫn field vào error. `ErrorType.NOT_FOUND` phân loại lỗi theo nhóm của Spring for GraphQL; `extensions.code` cung cấp mã ổn định để client xử lý mà không phải phân tích message.

Một số import liên quan:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.Map;
```

Không nên trả trực tiếp `ex.getMessage()` trong mọi trường hợp. Message exception có thể chứa ID nội bộ, câu truy vấn hoặc thông tin hệ thống. Hãy trả thông điệp an toàn, có ý nghĩa với client; chi tiết kỹ thuật có thể được ghi log phía server với correlation ID phù hợp.

## 5. Xử lý exception tập trung bằng `DataFetcherExceptionResolver`

Khi muốn xử lý exception ở cấp ứng dụng hoặc cần tùy chỉnh sâu hơn, có thể đăng ký `DataFetcherExceptionResolver`. `DataFetcherExceptionResolverAdapter` cung cấp cách triển khai thuận tiện cho trường hợp ánh xạ một exception thành một `GraphQLError`.

```java
@Component
class BookDataFetcherExceptionResolver extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
        }

        return null;
    }
}
```

Nếu resolver này không xử lý exception, trả về `null` để cơ chế xử lý tiếp theo có thể xử lý nó. Có thể dùng nhiều resolver với thứ tự ưu tiên phù hợp.

Nên chọn một nơi xử lý rõ ràng cho mỗi nhóm exception. `@GraphQlExceptionHandler` thuận tiện cho controller advice và xử lý theo annotation; `DataFetcherExceptionResolver` phù hợp với xử lý tập trung ở tầng GraphQL. Tránh tạo nhiều handler cùng bắt một exception nhưng trả mã và message không nhất quán.

## 6. Trả business error trong mutation payload

Không phải mọi trường hợp không thành công đều là lỗi thực thi. Ví dụ, người dùng gửi một ISBN đã tồn tại. Server vẫn xử lý đúng request, kiểm tra nghiệp vụ thành công và kết luận dữ liệu không thể được tạo. Đây là kết quả nghiệp vụ dự kiến, không nhất thiết phải tạo top-level `errors`.

Một mẫu phổ biến là trả payload luôn có danh sách `userErrors`:

```graphql
type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}

type CreateBookPayload {
    book: Book
    userErrors: [UserError!]!
}

type UserError {
    code: String!
    message: String!
    field: [String!]
}
```

`userErrors` luôn là danh sách, kể cả khi mutation thành công thì danh sách cũng có thể rỗng. `field` chỉ ra vị trí input liên quan đến lỗi, ví dụ `['input', 'isbn']`. `book` có thể là `null` nếu dữ liệu không được tạo.

Java record cho payload:

```java
public record UserError(
    String code,
    String message,
    List<String> field
) {}

public record CreateBookPayload(
    Book book,
    List<UserError> userErrors
) {}
```

Resolver có thể trả business error như một kết quả bình thường:

```java
@MutationMapping
CreateBookPayload createBook(@Argument("input") CreateBookInput input) {
    if (bookService.isIsbnTaken(input.isbn())) {
        UserError error = new UserError(
            "DUPLICATE_ISBN",
            "ISBN đã được sử dụng",
            List.of("input", "isbn")
        );
        return new CreateBookPayload(null, List.of(error));
    }

    Book created = bookService.create(input);
    return new CreateBookPayload(created, List.of());
}
```

Trong ví dụ này, lỗi trùng ISBN là một kết quả dự kiến nên resolver trả payload thay vì ném exception. Client có thể đọc `userErrors`, hiển thị message cạnh input và cho phép người dùng sửa dữ liệu.

Mutation thành công:

```graphql
mutation {
    createBook(input: {
        title: "GraphQL in Practice"
        isbn: "978-0000000001"
    }) {
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
```

Khi có business error, response vẫn có cấu trúc `data` bình thường:

```json
{
  "data": {
    "createBook": {
      "book": null,
      "userErrors": [
        {
          "code": "DUPLICATE_ISBN",
          "message": "ISBN đã được sử dụng",
          "field": ["input", "isbn"]
        }
      ]
    }
  }
}
```

Đây không phải top-level GraphQL execution error. Client không cần đọc `errors` để biết người dùng cần sửa trường nào.

## 7. Dùng Union để biểu diễn các kết quả mutation

Nếu mỗi loại kết quả có dữ liệu rất khác nhau, có thể dùng union thay cho một payload có nhiều field nullable:

```graphql
type Mutation {
    createBook(input: CreateBookInput!): CreateBookResult!
}

union CreateBookResult = CreateBookSuccess | CreateBookValidationFailure

type CreateBookSuccess {
    book: Book!
}

type CreateBookValidationFailure {
    errors: [UserError!]!
}
```

Client dùng inline fragment để xử lý từng nhánh:

```graphql
mutation {
    createBook(input: {
        title: "GraphQL in Practice"
        isbn: "978-0000000001"
    }) {
        __typename
        ... on CreateBookSuccess {
            book {
                id
                title
            }
        }
        ... on CreateBookValidationFailure {
            errors {
                code
                message
                field
            }
        }
    }
}
```

Union làm rõ các trạng thái kết quả bằng kiểu cụ thể. Đổi lại, server phải cấu hình type resolution cho các object Java được trả về và client cần xử lý các nhánh bằng `__typename`/inline fragment. Với mutation đơn giản, payload có `userErrors` thường dễ triển khai hơn; union phù hợp khi các kết quả thành công và thất bại có cấu trúc khác biệt rõ ràng.

## 8. Phân biệt lỗi validation của GraphQL và validation nghiệp vụ

GraphQL kiểm tra kiểu và cấu trúc input trước khi gọi resolver. Ví dụ:

```graphql
input CreateBookInput {
    title: String!
    isbn: String!
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}
```

Những trường hợp sau là request error:

- Không truyền argument `input` bắt buộc.
- Thiếu field `title` hoặc `isbn` có kiểu Non-null.
- Truyền giá trị không thể chuyển đổi sang kiểu GraphQL đã khai báo.
- Gửi field không tồn tại trong input object.

Trong các trường hợp này, GraphQL từ chối request trước khi gọi resolver. Không nên cố chuyển những lỗi kiểu GraphQL này thành `userErrors` trong payload, vì phương thức mutation chưa có cơ hội chạy.

Ngược lại, những quy tắc như tiêu đề phải duy nhất, ngày phát hành phải nằm trong khoảng cho phép hoặc người dùng không được tạo quá số lượng sách nhất định thường là validation nghiệp vụ. Chúng có thể được biểu diễn trong payload để client sửa và gửi lại.

Có thể dùng Bean Validation cho input Java nếu ứng dụng đã cấu hình Spring Validation. Khi validation ném exception, hãy quyết định rõ đây là lỗi đầu vào cần trả theo GraphQL error hay business error cần đưa vào payload. Giữ một chính sách nhất quán giữa các mutation để client không phải xử lý cùng một quy tắc theo nhiều dạng response khác nhau.

## 9. Transaction và tính nhất quán khi mutation gặp lỗi

Mutation root fields được GraphQL thực thi tuần tự theo thứ tự xuất hiện trong operation. Tuy nhiên, điều đó không tự tạo một transaction cơ sở dữ liệu bao trùm toàn bộ mutation operation.

Nếu một mutation thay đổi nhiều bản ghi cần tính nguyên tử, hãy đặt ranh giới transaction ở service:

```java
@Service
class OrderService {

    @Transactional
    Order createOrder(CreateOrderInput input) {
        // Validate trạng thái nghiệp vụ.
        // Lưu order và các order item trong cùng transaction.
        // Ném exception nếu thao tác cần rollback.
        return saveOrderAndItems(input);
    }
}
```

Khi service ném exception, transaction có thể rollback theo cấu hình Spring transaction; exception sau đó được chuyển thành GraphQL error hoặc được xử lý theo chính sách của ứng dụng. Nếu resolver trả `userErrors` như một kết quả bình thường, transaction không tự rollback chỉ vì payload có danh sách lỗi. Vì vậy, hãy kiểm tra điều kiện nghiệp vụ trước khi ghi dữ liệu hoặc chủ động rollback khi cần.

Nếu một operation chứa nhiều top-level mutation field và field sau thất bại, không nên giả định những thay đổi đã commit từ field trước sẽ tự động được rollback. Muốn nhiều thao tác là một đơn vị nguyên tử, hãy thiết kế một mutation tổng hợp và thực hiện toàn bộ công việc trong một service transaction.

## 10. Kiểm thử mutation error response

Kiểm thử nên phân biệt execution error với business error trong payload.

### Kiểm thử execution error

Ví dụ khi `BookNotFoundException` được ánh xạ bởi `@GraphQlExceptionHandler`:

```java
GraphQlTester.Response response = graphQlTester.document("""
        mutation {
            deleteBook(id: "missing-book") {
                id
            }
        }
        """)
    .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getExtensions())
        .containsEntry("code", "BOOK_NOT_FOUND");
});
response.path("deleteBook").valueIsNull();
```

Ví dụ minh họa; các import và cấu hình test context được lược bỏ. Assertion kiểm tra cả mã lỗi trong `extensions` và giá trị field bị lỗi. Có thể kiểm tra thêm `path` để bảo đảm lỗi gắn đúng mutation field.

### Kiểm thử business error trong payload

Khi ISBN trùng, resolver trả `CreateBookPayload` bình thường:

```java
graphQlTester.document("""
        mutation {
            createBook(input: {
                title: "GraphQL in Practice"
                isbn: "duplicate-isbn"
            }) {
                book { id }
                userErrors {
                    code
                    field
                }
            }
        }
        """)
    .execute()
    .path("createBook.userErrors[0].code")
    .entity(String.class)
    .isEqualTo("DUPLICATE_ISBN");
```

Với business error, response không cần có top-level `errors`; kiểm thử nên xác minh `userErrors`, `book` là `null` và service không ghi dữ liệu mới.

### Ma trận kiểm thử đề xuất

| Tình huống | Điều cần xác minh |
|---|---|
| Input thiếu field Non-null | Request bị từ chối; resolver không chạy. |
| Input đúng nhưng vi phạm quy tắc nghiệp vụ | `data` có payload và `userErrors` phù hợp. |
| Không tìm thấy đối tượng | Top-level error có code và path rõ ràng, hoặc kết quả có kiểu nếu đó là trạng thái dự kiến. |
| Database/service gặp sự cố | Client nhận lỗi an toàn; chi tiết nội bộ chỉ nằm trong log. |
| Người dùng không đủ quyền | Không thay đổi dữ liệu và response theo chính sách authorization. |
| Lỗi giữa một transaction | Các thay đổi trong transaction được rollback như mong đợi. |

## 11. Bảo mật và thiết kế mã lỗi

Client nên dựa vào mã lỗi ổn định như `BOOK_NOT_FOUND`, `DUPLICATE_ISBN` hoặc `ACCESS_DENIED`, thay vì so sánh chuỗi message. Message có thể được dịch, thay đổi cách diễn đạt hoặc bị rút gọn theo chính sách bảo mật.

Một số nguyên tắc quan trọng:

1. Không trả stack trace, SQL, tên bảng, thông tin kết nối hoặc dữ liệu nhạy cảm trong `message` hay `extensions`.
2. Chỉ đưa vào `extensions` metadata mà client thực sự cần để xử lý lỗi.
3. Không tiết lộ sự tồn tại của tài nguyên nếu chính sách bảo mật yêu cầu che giấu; ví dụ có thể trả cùng một thông điệp cho tài nguyên không tồn tại và tài nguyên người dùng không được phép xem.
4. Dùng log phía server để ghi chi tiết exception, kèm correlation ID hoặc trace ID để điều tra.
5. Chuẩn hóa mã lỗi và cấu trúc `userErrors` giữa các mutation để client tái sử dụng logic hiển thị và xử lý.

Không nên dùng HTTP status code làm cách duy nhất để xác định mutation thành công hay thất bại. GraphQL có thể trả một response hợp lệ ở tầng giao thức nhưng vẫn có `errors` ở tầng thực thi; business error trong payload thậm chí có thể xuất hiện trong `data` mà không có `errors`. Client cần đọc nội dung GraphQL response theo hợp đồng API.

## 12. Những lỗi thường gặp

**Ném exception cho mọi lỗi nghiệp vụ.** Điều này khiến các trường hợp người dùng có thể sửa trở thành execution error. Cân nhắc payload có `userErrors` cho validation dự kiến.

**Trả business error dưới dạng message exception không có cấu trúc.** Client buộc phải phân tích message và dễ bị hỏng khi nội dung thay đổi. Dùng mã lỗi ổn định và field path.

**Quên xử lý null propagation.** Nếu mutation trả kiểu Non-null nhưng resolver trả `null`, GraphQL tạo lỗi và có thể làm mất dữ liệu ở cấp cha. Chọn kiểu SDL phù hợp với mọi trạng thái kết quả.

**Đưa message exception thô ra client.** Exception có thể chứa thông tin nhạy cảm. Ánh xạ sang message an toàn và ghi chi tiết ở server.

**Cho rằng lỗi trong payload sẽ tự rollback transaction.** Payload là kết quả bình thường của resolver. Hãy chủ động quản lý transaction và điều kiện rollback.

**Kiểm tra lỗi chỉ bằng HTTP status.** Hãy kiểm tra `data`, `errors`, `path`, `extensions` hoặc `userErrors` theo loại lỗi.

**Để các mutation trả lỗi theo nhiều cấu trúc khác nhau.** Chuẩn hóa mã và payload giúp client dễ xử lý và giảm logic đặc thù ở từng màn hình.

## Kết luận

Mutation error response trong Spring for GraphQL cần phân biệt request error, execution error và business error dự kiến. Dùng `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver` để chuyển exception thành `GraphQLError` an toàn; dùng payload có `userErrors` hoặc union kết quả khi client cần xử lý trạng thái nghiệp vụ như một phần của response. Kết hợp mã lỗi ổn định, nullability phù hợp, transaction rõ ràng và kiểm thử bằng `GraphQlTester` để mutation có hành vi nhất quán, dễ hiểu và an toàn cho client.
