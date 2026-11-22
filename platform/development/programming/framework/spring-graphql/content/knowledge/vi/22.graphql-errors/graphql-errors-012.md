# Partial data và errors trong Spring for GraphQL

Một GraphQL operation có thể trả về dữ liệu của những field resolve thành công, đồng thời trả lỗi cho field thất bại. Đây là đặc điểm quan trọng của GraphQL: lỗi khi thực thi một field không nhất thiết làm hỏng toàn bộ query. Response có thể chứa cả `data` và `errors`; client cần đọc cả hai để biết phần dữ liệu nào dùng được và phần nào không hoàn chỉnh.

Trong Spring for GraphQL, exception phát sinh từ annotated controller hoặc data fetcher được đưa vào cơ chế xử lý lỗi của GraphQL. Ứng dụng có thể chuyển exception thành GraphQL error bằng `@GraphQlExceptionHandler`, `DataFetcherExceptionResolver` hoặc chủ động trả `DataFetcherResult` khi muốn cung cấp dữ liệu kèm lỗi. Kết quả cuối cùng còn phụ thuộc nullability trong SDL và quy tắc null propagation của GraphQL.

## 1. Vì sao GraphQL có partial data?

Giả sử schema thư viện có query lấy sách cùng tác giả và đánh giá:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author
    reviews: [Review!]!
}

type Author {
    id: ID!
    name: String!
}

type Review {
    id: ID!
    comment: String!
}
~~~

Client gửi:

~~~graphql
query BookDetails($id: ID!) {
    book(id: $id) {
        id
        title
        author {
            id
            name
        }
        reviews {
            id
            comment
        }
    }
}
~~~

Giả sử resolver `book` trả về sách, resolver `reviews` tải được đánh giá, nhưng dịch vụ tác giả bị lỗi. Vì `Book.author` là nullable, GraphQL có thể trả về `author: null` và giữ lại các field khác:

~~~json
{
    "data": {
        "book": {
            "id": "book-1",
            "title": "Spring for GraphQL",
            "author": null,
            "reviews": [
                {
                    "id": "review-1",
                    "comment": "Clear examples"
                }
            ]
        }
    },
    "errors": [
        {
            "message": "Author service is unavailable",
            "locations": [
                { "line": 6, "column": 9 }
            ],
            "path": ["book", "author"]
        }
    ]
}
~~~

Response vẫn có `data` vì một phần query đã thực thi thành công. `errors` mô tả field không thể resolve. Client có thể hiển thị tiêu đề và reviews, đồng thời thể hiện khu vực tác giả chưa tải được.

## 2. Phân biệt request errors và execution errors

GraphQL errors thường được chia thành hai nhóm theo thời điểm xảy ra:

| Loại lỗi | Thời điểm | Có thực thi resolver không? | Response data |
| --- | --- | --- | --- |
| Request error | Parse document, validate schema hoặc coerce variables | Không | Không có key `data` |
| Execution error | Khi một field resolver hoặc quá trình serialize giá trị thực thi | Có, ít nhất một phần operation | Có thể có `data` một phần hoặc `data: null` do null propagation |

Ví dụ request error: client gọi field không tồn tại hoặc truyền sai kiểu argument. GraphQL từ chối operation trước khi chạy resolver, nên không có dữ liệu field nào được tạo ra.

Ví dụ execution error: query hợp lệ, resolver `book` trả dữ liệu nhưng resolver `author` ném exception. GraphQL ghi lỗi vào `errors` và xử lý phần `data` theo nullability của schema.

Điều này giải thích vì sao `errors` không đồng nghĩa toàn bộ operation thất bại. Client cần kiểm tra cả `data` và `errors`, thay vì chỉ dựa vào HTTP status hoặc coi mọi response có `errors` là không có dữ liệu.

## 3. Cấu trúc GraphQL error

Một error trong response GraphQL có thể có các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `message` | Mô tả ngắn gọn lỗi dành cho client |
| `locations` | Vị trí dòng/cột trong GraphQL document liên quan đến lỗi, nếu xác định được |
| `path` | Đường dẫn đến field hoặc list item bị lỗi trong response |
| `extensions` | Metadata bổ sung do implementation hoặc ứng dụng định nghĩa |

Ví dụ error của field con:

~~~json
{
    "message": "Author is not available",
    "locations": [{ "line": 6, "column": 9 }],
    "path": ["book", "author"],
    "extensions": {
        "code": "AUTHOR_UNAVAILABLE"
    }
}
~~~

`path` dùng tên response key, nên nếu client đặt alias cho field, path thường chứa alias đó. Với field nằm trong list, path còn có chỉ số phần tử, ví dụ `["books", 2, "author"]`. Điều này giúp client xác định chính xác vị trí dữ liệu bị thiếu.

`extensions` không có một tập key nghiệp vụ cố định cho mọi ứng dụng. Hãy chọn cấu trúc nhất quán, chẳng hạn `code`, `correlationId` hoặc `retryable`, và tránh đưa stack trace, câu SQL, tên bảng hay thông tin nội bộ vào response.

## 4. Nullability quyết định partial data lan truyền ra sao

GraphQL dùng `null` để biểu diễn field không có kết quả. Khi một field bị lỗi trong lúc thực thi, GraphQL xem kết quả của field đó là `null` rồi áp dụng quy tắc Non-Null trong schema.

Với field nullable, lỗi chỉ làm field đó thành `null`; các field sibling vẫn có thể được resolve. Với field có dấu `!`, `null` không hợp lệ nên lỗi lan lên parent gần nhất có thể nhận `null`. Quá trình này tiếp tục cho đến khi gặp một field nullable hoặc chạm đến root, khi đó `data` có thể trở thành `null`.

Ví dụ:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author
}
~~~

`author` nullable nên khi resolver lỗi, `book.author` trở thành `null`; `book.id` và `book.title` vẫn giữ được.

Nếu schema đổi thành:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author!
}
~~~

Resolver `author` không thể trả `null`. Nếu nó lỗi, giá trị null lan lên `Book`. Nếu root field `Query.book` nullable, `data.book` có thể là `null`, nhưng các root field khác trong cùng operation vẫn có thể giữ dữ liệu.

## 5. Null propagation với list

List có hai vị trí nullability độc lập: bản thân list và từng item.

| SDL | List có thể null? | Item có thể null? | Nếu một item resolver lỗi |
| --- | --- | --- | --- |
| `[Review]` | Có | Có | Item đó thành `null`, các item khác giữ nguyên |
| `[Review!]` | Có | Không | Toàn bộ list thành `null` |
| `[Review]!` | Không | Có | Item đó thành `null`, list vẫn còn |
| `[Review!]!` | Không | Không | List thành `null`, sau đó null tiếp tục lan lên parent |

Ví dụ `reviews: [Review!]!` yêu cầu list và mọi item đều không null. Nếu một item không thể resolve, GraphQL không thể chỉ đặt item đó thành null; toàn bộ list trở thành null. Vì field `reviews` cũng Non-Null, null tiếp tục lan lên object cha.

Nullability do đó là một phần của thiết kế độ tin cậy API. Chọn Non-Null cho field chỉ khi ứng dụng có thể bảo đảm giá trị luôn tồn tại trong mọi tình huống được phép. Với quan hệ phụ thuộc dịch vụ ngoài hoặc dữ liệu có thể bị thiếu, nullable field đôi khi giúp giữ lại nhiều partial data hơn.

## 6. Resolver có thể ném exception

Một annotated controller có thể ném exception khi không tải được dữ liệu:

~~~java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId())
                .orElseThrow(() -> new AuthorUnavailableException(
                        "Author service is unavailable"
                ));
    }
}
~~~

Exception từ data fetcher được GraphQL Java xử lý thành execution error. Spring for GraphQL cung cấp cơ chế exception resolver để chuyển exception sang `GraphQLError` có thông tin phù hợp.

Không nên bắt mọi exception rồi trả `null` một cách im lặng:

~~~java
// Không nên: làm mất thông tin lỗi và khiến client không biết vì sao field null.
try {
    return authorService.findById(book.authorId()).orElse(null);
}
catch (Exception ex) {
    return null;
}
~~~

Nếu `null` là kết quả hợp lệ theo nghiệp vụ, trả null là đủ. Nếu có lỗi hệ thống hoặc nghiệp vụ cần thông báo cho client, hãy để exception đi vào error handling và giữ lại path, error code phù hợp.

## 7. Xử lý exception bằng @GraphQlExceptionHandler

`@GraphQlExceptionHandler` cho phép xử lý exception trong controller hoặc trong một class `@ControllerAdvice`. Đây là cách thuận tiện để ánh xạ exception nghiệp vụ thành GraphQL error.

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleAuthorUnavailable(
            AuthorUnavailableException exception,
            DataFetchingEnvironment environment
    ) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.INTERNAL_ERROR)
                .message("Author information is temporarily unavailable")
                .extensions(java.util.Map.of(
                        "code", "AUTHOR_UNAVAILABLE"
                ))
                .build();
    }
}
~~~

`GraphqlErrorBuilder.newError(environment)` tạo error gắn với field đang được resolve, nhờ đó GraphQL có thể điền `locations` và `path`. `ErrorType` của Spring for GraphQL cung cấp phân loại lỗi chuẩn hóa; `extensions` cho phép bổ sung mã lỗi riêng của ứng dụng.

Nên trả message đã được kiểm soát, không trả nguyên văn exception nếu nó chứa thông tin hạ tầng. Exception gốc vẫn có thể được ghi log ở server với correlation ID.

## 8. Xử lý lỗi toàn cục bằng DataFetcherExceptionResolver

Khi muốn áp dụng quy tắc chung cho nhiều controller, có thể triển khai `DataFetcherExceptionResolver`. Spring for GraphQL gọi resolver khi data fetcher phát sinh exception.

Ví dụ dùng adapter để ánh xạ exception đã biết:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

@Component
public class BookExceptionResolver extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment
    ) {
        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .errorType(ErrorType.NOT_FOUND)
                    .message("Book was not found")
                    .extensions(java.util.Map.of("code", "BOOK_NOT_FOUND"))
                    .build();
        }

        return null;
    }
}
~~~

Trả `null` từ `resolveToSingleError` có nghĩa resolver này không xử lý exception đó; Spring có thể chuyển tiếp cho resolver khác. Nếu không có resolver nào xử lý, lỗi sẽ đi vào cơ chế xử lý mặc định của GraphQL Java/Spring for GraphQL.

Chọn `@GraphQlExceptionHandler` khi logic gắn với controller hoặc nhóm controller. Chọn `DataFetcherExceptionResolver` khi muốn một chính sách tập trung, độc lập với annotated controller. Tránh đăng ký nhiều nơi cùng xử lý một exception theo các quy tắc mâu thuẫn.

## 9. Chủ động trả data kèm errors bằng DataFetcherResult

Không phải mọi tình huống đều cần ném exception. Khi resolver có thể trả dữ liệu nhưng đồng thời muốn báo một lỗi hoặc cảnh báo gắn với field, GraphQL Java cung cấp `DataFetcherResult<T>`.

~~~java
import graphql.GraphqlErrorBuilder;
import graphql.execution.DataFetcherResult;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public DataFetcherResult<Book> book(
            @Argument("id") Long id,
            DataFetchingEnvironment environment
    ) {
        Book book = bookService.findById(id);

        return DataFetcherResult.<Book>newResult()
                .data(book)
                .error(GraphqlErrorBuilder.newError(environment)
                        .message("Some optional book metadata could not be loaded")
                        .extensions(java.util.Map.of("code", "METADATA_UNAVAILABLE"))
                        .build())
                .build();
    }
}
~~~

Ví dụ này minh họa cách trả data cùng errors từ một data fetcher. Trong ứng dụng thực tế, chỉ thêm error khi thật sự có một vấn đề cần client biết; nếu metadata tùy chọn không được client yêu cầu hoặc không ảnh hưởng response, không nhất thiết phải tạo lỗi.

`DataFetcherResult` còn hỗ trợ local context và extensions. Nó hữu ích khi muốn trả kết quả có kiểm soát từ resolver. Với lỗi exception thông thường, không cần tự dựng `DataFetcherResult`; exception resolver phù hợp hơn.

## 10. Partial data khi một field trong list bị lỗi

Giả sử query trả nhiều sách, mỗi sách có tác giả nullable:

~~~graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: Author
}
~~~

Nếu resolver `Book.author` lỗi với một sách, response có thể giữ toàn bộ list sách, trong khi field author của phần tử đó là null:

~~~json
{
    "data": {
        "books": [
            {
                "id": "book-1",
                "title": "GraphQL Basics",
                "author": { "id": "author-1", "name": "An" }
            },
            {
                "id": "book-2",
                "title": "Spring GraphQL",
                "author": null
            }
        ]
    },
    "errors": [
        {
            "message": "Author information is temporarily unavailable",
            "path": ["books", 1, "author"]
        }
    ]
}
~~~

Vì `Book.author` nullable, lỗi chỉ ảnh hưởng field con của phần tử thứ hai. Nếu `author` là `Author!`, lỗi sẽ làm phần tử `Book` tương ứng thành null; nhưng `books` khai báo `[Book!]!` nên item null không hợp lệ, khiến toàn bộ list null rồi tiếp tục lan lên parent.

## 11. Không dùng errors để thay thế kết quả nghiệp vụ bình thường

Không phải trường hợp không có dữ liệu nào cũng là lỗi. Ví dụ:

- Không tìm thấy sách theo ID có thể là kết quả `null` hợp lệ nếu schema khai báo `Book` nullable.
- Danh sách rỗng có thể là kết quả hợp lệ của query tìm kiếm.
- Một bộ lọc không có kết quả không nhất thiết cần thêm GraphQL error.
- Không đủ quyền truy cập là tình huống cần xử lý theo chính sách authorization; có thể trả lỗi FORBIDDEN hoặc che giấu sự tồn tại của tài nguyên tùy yêu cầu bảo mật.

Hãy phân biệt absence, validation failure, business conflict và infrastructure failure. Nếu mọi tình huống đều trở thành `INTERNAL_ERROR`, client khó đưa ra hành vi phù hợp và telemetry khó phân loại vấn đề.

## 12. Thiết kế error code và extensions

Client thường cần mã ổn định hơn message tự do để quyết định có hiển thị nút thử lại, yêu cầu đăng nhập hay chuyển trang. Có thể chuẩn hóa extensions:

~~~json
{
    "message": "Author information is temporarily unavailable",
    "path": ["book", "author"],
    "extensions": {
        "code": "AUTHOR_UNAVAILABLE",
        "retryable": true,
        "correlationId": "req-123"
    }
}
~~~

Một số quy tắc:

1. `code` nên ổn định và được tài liệu hóa.
2. `message` nên hướng tới client và không chứa chi tiết nội bộ.
3. `retryable` chỉ nên là `true` nếu retry có ý nghĩa và an toàn.
4. `correlationId` giúp nối response với log server.
5. Không đưa token, cookie, stack trace, SQL, tên host hoặc thông tin cá nhân không cần thiết vào `extensions`.

Đừng buộc client phân tích nội dung `message` để nhận diện loại lỗi. Message có thể được bản địa hóa hoặc thay đổi; `code` mới là hợp đồng máy đọc phù hợp hơn.

## 13. HTTP status và GraphQL errors

GraphQL response body và HTTP status giải quyết hai lớp khác nhau. Một operation hợp lệ có thể được thực thi và trả `data` một phần cùng `errors`; điều đó thường vẫn là một GraphQL response hợp lệ ở tầng transport.

Không nên giả định mọi execution error phải biến HTTP status thành 4xx hoặc 5xx. Với HTTP GraphQL, status còn phụ thuộc giai đoạn lỗi, media type, transport và cấu hình server. Client nên đọc GraphQL response body theo giao thức thay vì chỉ kiểm tra status code.

Ví dụ, resolver `author` lỗi nhưng `book.title` vẫn có dữ liệu: client có thể tiếp tục hiển thị phần dữ liệu hợp lệ. Ngược lại, lỗi parse hoặc validation xảy ra trước execution thì không có field data để sử dụng.

## 14. Kiểm thử partial data và errors bằng GraphQlTester

`GraphQlTester` cho phép kiểm tra cả dữ liệu và danh sách lỗi. Ví dụ query có `Book.author` nullable, service tác giả ném exception và exception advice chuyển nó thành error có mã ổn định.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;

@GraphQlTest({BookQueryController.class, BookController.class, GraphQlExceptionAdvice.class})
class PartialDataTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    @Test
    void keepsBookDataWhenAuthorResolverFails() {
        given(bookService.findById(1L))
                .willReturn(new Book(1L, "Spring for GraphQL", 10L));
        given(authorService.findById(10L))
                .willThrow(new AuthorUnavailableException("downstream timeout"));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    book(id: 1) {
                        id
                        title
                        author { id name }
                    }
                }
                """)
                .execute();

        response.path("book.title")
                .entity(String.class)
                .isEqualTo("Spring for GraphQL");
        response.path("book.author")
                .valueIsNull();
        response.errors().satisfy(errors -> {
            org.assertj.core.api.Assertions.assertThat(errors).hasSize(1);
            org.assertj.core.api.Assertions.assertThat(errors.get(0).getPath())
                    .containsExactly("book", "author");
        });
    }
}
~~~

Ví dụ giả định schema SDL đã được nạp và các controller/advice dùng các service tương ứng. `Book` có constructor `(Long id, String title, Long authorId)`. Tùy cấu hình Spring Boot 3.x/4.x, annotation mock bean có thể dùng `@MockitoBean` hoặc cơ chế mock bean tương ứng của phiên bản.

Nên kiểm thử thêm:

1. Nullable field lỗi nhưng sibling field vẫn có dữ liệu.
2. Non-Null field lỗi và null propagation lên đúng parent.
3. Một item trong list lỗi với từng kiểu `[T]`, `[T!]`, `[T]!`, `[T!]!`.
4. Request validation error không chạy resolver.
5. Error code và extensions ổn định, không lộ thông tin nội bộ.
6. Alias và list index xuất hiện đúng trong `path`.
7. `DataFetcherResult` trả data kèm error như dự kiến.

## 15. Lỗi thường gặp khi xử lý partial data

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Toàn bộ `data` thành null | Non-Null field lỗi và null lan đến root | Kiểm tra chuỗi `!` trong SDL; chỉ dùng Non-Null khi có thể bảo đảm giá trị |
| Field null nhưng không có error | Resolver chủ động trả null hoặc lỗi bị bắt và nuốt | Phân biệt absence hợp lệ với lỗi; không nuốt exception không có chủ đích |
| `errors` có nhưng client bỏ qua | Client chỉ đọc `data` hoặc chỉ kiểm tra HTTP status | Xử lý đồng thời `data` và `errors`, dùng `path` để xác định field lỗi |
| Path không giống tên field trong SDL | Client dùng alias hoặc field nằm trong list | Đọc response path, bao gồm alias và chỉ số list |
| Error message làm lộ hạ tầng | Trả trực tiếp `exception.getMessage()` | Dùng message an toàn và error code ổn định |
| Exception không được ánh xạ | Exception handler/resolver không nhận đúng loại hoặc không được đăng ký | Kiểm tra `@ControllerAdvice`, `@GraphQlExceptionHandler` và resolver beans |
| Lỗi nghiệp vụ bình thường bị báo như server error | Dùng một exception chung cho mọi tình huống | Phân loại not-found, forbidden, validation và infrastructure failure |
| List bị null ngoài dự kiến | Item type hoặc list type khai báo Non-Null | Xem lại `[T]`, `[T!]`, `[T]!`, `[T!]!` và contract dữ liệu |

## 16. Quy trình thiết kế partial data và errors

Khi thiết kế GraphQL API có nhiều field phụ thuộc:

1. Xác định field nào có thể thiếu hoặc thất bại độc lập.
2. Chọn nullable/Non-Null theo khả năng bảo đảm dữ liệu, không chỉ theo mong muốn client.
3. Hiểu null propagation từ field đến list, parent và root.
4. Dùng exception handler hoặc `DataFetcherExceptionResolver` để chuẩn hóa lỗi thực thi.
5. Dùng `DataFetcherResult` khi cần trả dữ liệu cùng lỗi một cách chủ động.
6. Chuẩn hóa `extensions.code` và message an toàn cho client.
7. Phân biệt request errors với execution errors.
8. Kiểm thử cả partial `data`, `errors`, `path` và null propagation bằng `GraphQlTester`.
9. Thiết kế client đọc đồng thời dữ liệu và lỗi, không phụ thuộc duy nhất vào HTTP status.

Partial data là một khả năng quan trọng của GraphQL, giúp client vẫn sử dụng được những field thành công khi một nhánh gặp sự cố. Để hành vi này rõ ràng, schema phải có nullability phù hợp, server phải gắn lỗi đúng field và client phải xử lý cả `data` lẫn `errors`.

## Tài liệu tham khảo

- [GraphQL Specification — Response Format](https://spec.graphql.org/October2021/#sec-Response-Format)
- [GraphQL Specification — Handling Field Errors](https://spec.graphql.org/October2021/#sec-Handling-Field-Errors)
- [Spring for GraphQL — Exceptions](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers-exceptions)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
