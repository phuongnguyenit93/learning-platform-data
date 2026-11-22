# @QueryMapping cho Query field

Trong Spring for GraphQL, **@QueryMapping** dùng để nối một method Java trong controller với một field thuộc root object type Query của GraphQL schema. Khi client gọi field đó trong query operation, Spring chuyển việc phân giải field đến method tương ứng, bind các argument và dùng giá trị method trả về để tạo response.

Annotation này giúp viết GraphQL controller theo cách quen thuộc của Spring, đồng thời giữ schema SDL làm hợp đồng API. Bài học trình bày cách khai báo mapping, nhận argument, trả về object hoặc danh sách, xử lý kết quả bất đồng bộ, tổ chức service, xử lý lỗi và kiểm thử Query field.

## 1. @QueryMapping là gì?

GraphQL schema khai báo root type Query cho các thao tác đọc dữ liệu:

~~~graphql
type Query {
    book(id: ID!): Book
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
}
~~~

Schema mô tả hai field mà client có thể gọi:

- `book` nhận argument `id` và trả về một Book hoặc null.
- `books` không nhận argument và trả về một list Book không null, trong đó từng phần tử cũng không null.

Trong Spring for GraphQL, có thể viết controller:

~~~java
@Controller
public class BookQueryController {

    @QueryMapping
    public Book book(@Argument("id") String id) {
        // Tìm sách theo id
        return bookService.findById(id);
    }

    @QueryMapping
    public List<Book> books() {
        // Lấy danh sách sách
        return bookService.findAll();
    }
}
~~~

`@QueryMapping` là annotation chuyên biệt cho field trên root Query. Về bản chất, nó là cách viết ngắn của `@SchemaMapping(typeName = "Query")`.

Khi method được Spring phát hiện, Spring đăng ký method đó như một DataFetcher cho field tương ứng. GraphQL Java gọi DataFetcher khi thực thi operation có chọn field này.

### Phân biệt schema và mapping

Hai phần cần được khai báo đồng bộ:

| Thành phần | Vai trò |
| --- | --- |
| SDL `type Query` | Công bố field, argument và kiểu trả về cho client. |
| `@QueryMapping` | Nối field Query với method Java xử lý field. |
| `@Argument` | Lấy argument của field và bind vào tham số method. |
| Service | Thực hiện nghiệp vụ và truy cập dữ liệu. |

`@QueryMapping` không tự tạo field mới trong schema. Nếu controller có method `@QueryMapping` tên `book` nhưng schema không khai báo `Query.book`, ứng dụng có thể gặp lỗi khi xây dựng GraphQL runtime hoặc mapping không được gắn với field hợp lệ. Hãy khai báo SDL và controller cùng một hợp đồng.

## 2. Tạo một Query field hoàn chỉnh

Giả sử ứng dụng quản lý danh mục sách. Schema SDL:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    description: String
}
~~~

Một Java record biểu diễn dữ liệu:

~~~java
package com.example.catalog.book;

public record Book(
        String id,
        String title,
        String description
) {
}
~~~

Service:

~~~java
package com.example.catalog.book;

import org.springframework.stereotype.Service;

@Service
public class BookService {

    public Book findById(String id) {
        // Thay bằng truy vấn repository trong ứng dụng thực tế.
        if ("book-42".equals(id)) {
            return new Book(
                    "book-42",
                    "Spring in Action",
                    "A practical guide to Spring"
            );
        }
        return null;
    }
}
~~~

Controller:

~~~java
package com.example.catalog.graphql;

import com.example.catalog.book.Book;
import com.example.catalog.book.BookService;
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
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

Client gửi operation:

~~~graphql
query BookDetail($id: ID!) {
    book(id: $id) {
        id
        title
        description
    }
}
~~~

Variables:

~~~json
{
    "id": "book-42"
}
~~~

Response:

~~~json
{
    "data": {
        "book": {
            "id": "book-42",
            "title": "Spring in Action",
            "description": "A practical guide to Spring"
        }
    }
}
~~~

Quá trình xử lý diễn ra như sau:

1. Client gửi query document và variables đến GraphQL endpoint.
2. GraphQL Java kiểm tra operation theo schema.
3. GraphQL engine thực thi field `Query.book`.
4. Spring gọi method `book` đã được đánh dấu `@QueryMapping`.
5. `@Argument("id")` cung cấp giá trị `book-42` cho tham số Java.
6. Controller gọi service và trả về Book.
7. GraphQL engine phân giải các field `id`, `title`, `description` được client chọn.
8. Transport trả GraphQL response cho client.

## 3. Quy tắc đặt tên field và method

Mặc định, Spring dùng tên method làm tên field nếu annotation không chỉ rõ tên khác.

~~~graphql
type Query {
    recentBooks: [Book!]!
}
~~~

~~~java
@QueryMapping
public List<Book> recentBooks() {
    return bookService.findRecent();
}
~~~

Method `recentBooks` được ánh xạ tới `Query.recentBooks`.

Nếu tên method Java khác tên field SDL, dùng thuộc tính `name`:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

~~~java
@QueryMapping(name = "book")
public Book findBookById(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}
~~~

Ở ví dụ này, tên method là `findBookById`, còn field GraphQL là `book`. Thuộc tính `name` làm rõ mapping.

Tên GraphQL field thường dùng lower camelCase. Cần giữ tên field nhất quán giữa SDL, operation client và controller. GraphQL phân biệt chữ hoa và chữ thường, vì vậy `recentBooks` và `recentbooks` là hai tên khác nhau.

### Khi root Query có tên khác

Theo quy ước mặc định, root query type có tên `Query`. `@QueryMapping` được thiết kế để ánh xạ vào type này.

Nếu schema cố ý đặt tên root type khác, chẳng hạn:

~~~graphql
schema {
    query: CatalogQuery
}

type CatalogQuery {
    book(id: ID!): Book
}
~~~

có thể dùng `@SchemaMapping` với tên type tùy chỉnh:

~~~java
@SchemaMapping(typeName = "CatalogQuery", field = "book")
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

Với schema thông thường, nên giữ root type tên Query và dùng `@QueryMapping` để controller thể hiện rõ đây là thao tác đọc ở root.

## 4. Nhận argument bằng @Argument

Argument được khai báo trong SDL và bind vào tham số method bằng `@Argument`.

Schema:

~~~graphql
type Query {
    book(id: ID!): Book
    booksByAuthor(authorId: ID!): [Book!]!
}
~~~

Controller:

~~~java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}

@QueryMapping
public List<Book> booksByAuthor(
        @Argument("authorId") String authorId) {
    return bookService.findByAuthorId(authorId);
}
~~~

Tên truyền vào `@Argument` phải khớp với argument trong SDL. Việc ghi rõ tên argument giúp code không phụ thuộc vào tên tham số Java có được giữ lại khi biên dịch hay không.

Có thể bỏ tên trong annotation khi cơ chế khám phá parameter name của ứng dụng được cấu hình phù hợp:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

Trong code dùng cho dự án lớn hoặc khi muốn mapping rõ ràng, ghi `@Argument("id")` thường dễ đọc hơn.

### Nhiều argument trên một field

Schema:

~~~graphql
type Query {
    books(
        keyword: String
        limit: Int = 20
        offset: Int = 0
    ): [Book!]!
}
~~~

Controller:

~~~java
@QueryMapping
public List<Book> books(
        @Argument("keyword") String keyword,
        @Argument("limit") Integer limit,
        @Argument("offset") Integer offset) {
    return bookService.search(keyword, limit, offset);
}
~~~

Các giá trị mặc định trong SDL được GraphQL áp dụng khi argument bị bỏ qua. Tuy nhiên, `limit` và `offset` vẫn cần được kiểm tra ở lớp nghiệp vụ. Kiểu `Int` không tự giới hạn giá trị dương hay số lượng kết quả tối đa.

Ví dụ, service có thể chuẩn hóa giới hạn:

~~~java
public List<Book> search(String keyword, Integer limit, Integer offset) {
    int safeLimit = limit == null ? 20 : Math.min(Math.max(limit, 1), 100);
    int safeOffset = offset == null ? 0 : Math.max(offset, 0);

    return bookRepository.search(keyword, safeLimit, safeOffset);
}
~~~

Giới hạn cụ thể phụ thuộc yêu cầu ứng dụng. Không nên tin rằng client luôn truyền giá trị hợp lệ chỉ vì argument có kiểu số nguyên.

## 5. Bind input object vào tham số method

Khi Query có nhiều điều kiện lọc, dùng input object để gom dữ liệu đầu vào.

SDL:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}

input BookFilterInput {
    keyword: String
    genre: BookGenre
    authorId: ID
}

type Query {
    books(filter: BookFilterInput): [Book!]!
}
~~~

Java DTO:

~~~java
package com.example.catalog.book;

public record BookFilterInput(
        String keyword,
        BookGenre genre,
        String authorId
) {
}
~~~

Controller:

~~~java
@QueryMapping
public List<Book> books(@Argument("filter") BookFilterInput filter) {
    return bookService.search(filter);
}
~~~

Client gửi:

~~~graphql
query SearchBooks($filter: BookFilterInput) {
    books(filter: $filter) {
        id
        title
    }
}
~~~

Variables:

~~~json
{
    "filter": {
        "keyword": "Spring",
        "genre": "TECHNOLOGY"
    }
}
~~~

Spring for GraphQL bind input object theo cấu trúc schema sang Java class hoặc record tương ứng. Tên field và kiểu dữ liệu của DTO cần tương thích với SDL. Nếu schema dùng enum, Java enum tương ứng giúp code nghiệp vụ tránh phải xử lý chuỗi tùy ý.

Với input object có field lồng nhau, khai báo DTO lồng nhau theo cùng cấu trúc. Cần kiểm thử binding khi field bị bỏ qua, được truyền null hoặc dùng default value, đặc biệt với thao tác cập nhật.

## 6. Giá trị trả về của @QueryMapping

Method `@QueryMapping` có thể trả về nhiều dạng dữ liệu, miễn là phù hợp kiểu field trong schema và được Spring for GraphQL hỗ trợ.

### Trả về một object

SDL:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Java:

~~~java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

Nếu không tìm thấy sách, method có thể trả null vì kiểu trả về `Book` cho phép null.

Nếu schema khai báo `Book!`, resolver phải trả về object khác null. Nếu method trả null hoặc phát sinh lỗi, GraphQL áp dụng quy tắc non-null propagation và có thể làm field cha trở thành null.

### Trả về list

SDL:

~~~graphql
type Query {
    books: [Book!]!
}
~~~

Java:

~~~java
@QueryMapping
public List<Book> books() {
    return bookService.findAll();
}
~~~

Schema `[Book!]!` có hai cam kết:

- Field list không được null.
- Từng phần tử trong list không được null.

List rỗng vẫn hợp lệ. Nếu không có sách, nên trả collection rỗng thay vì null để giữ đúng hợp đồng.

### Trả về scalar hoặc enum

Không phải Query field nào cũng trả object:

~~~graphql
type Query {
    totalBooks: Int!
    isCatalogEmpty: Boolean!
    currentGenre: BookGenre
}
~~~

~~~java
@QueryMapping
public Integer totalBooks() {
    return bookService.count();
}

@QueryMapping
public Boolean isCatalogEmpty() {
    return bookService.count() == 0;
}

@QueryMapping
public BookGenre currentGenre() {
    return BookGenre.TECHNOLOGY;
}
~~~

Scalar và enum là leaf type nên client chọn trực tiếp, không cần selection set con.

### Trả về kiểu bất đồng bộ

Spring for GraphQL hỗ trợ các kiểu kết quả bất đồng bộ như `CompletionStage` và các kiểu reactive được hỗ trợ.

Ví dụ với `CompletableFuture`:

~~~java
@QueryMapping
public CompletableFuture<Book> book(@Argument("id") String id) {
    return CompletableFuture.supplyAsync(
            () -> bookService.findById(id),
            bookExecutor
    );
}
~~~

Ví dụ reactive với `Mono`:

~~~java
@QueryMapping
public Mono<Book> book(@Argument("id") String id) {
    return bookService.findByIdReactive(id);
}
~~~

Kiểu trả về phải phù hợp với kiến trúc ứng dụng. Không nên tự tạo thread pool hoặc dùng `supplyAsync` mặc định cho mọi resolver mà không quản lý executor, giới hạn tài nguyên và vòng đời tác vụ. Nếu service đã hỗ trợ reactive, giữ luồng reactive xuyên suốt thường dễ kiểm soát hơn.

## 7. Tách controller và service

Controller GraphQL nên tập trung vào việc nhận argument, gọi nghiệp vụ và trả kết quả. Service chịu trách nhiệm quy tắc nghiệp vụ và truy cập dữ liệu.

Ví dụ:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
~~~

Một số nguyên tắc tổ chức:

- Dùng constructor injection để khai báo dependency rõ ràng.
- Không đặt truy vấn SQL hoặc logic nghiệp vụ dài trong controller.
- Dùng DTO/input object khi argument có cấu trúc.
- Trả về object phù hợp với output type của schema.
- Giữ tên method và field rõ nghĩa.
- Tái sử dụng service giữa GraphQL controller và các adapter khác nếu nghiệp vụ giống nhau.

Cách tổ chức này giúp kiểm thử controller và service độc lập. Khi thay đổi transport hoặc thêm một API adapter khác, logic nghiệp vụ vẫn được giữ trong service.

## 8. Query field nên giữ ngữ nghĩa đọc dữ liệu

Root Query được dùng để đọc dữ liệu. Một query có thể được gọi nhiều lần, cache hoặc thực thi song song tùy client và server. Vì vậy, resolver Query không nên tạo side effect như tạo đơn hàng, cập nhật trạng thái hay xóa dữ liệu.

Ví dụ, thao tác đổi tên sách nên là Mutation:

~~~graphql
type Mutation {
    renameBook(id: ID!, title: String!): Book!
}
~~~

Không nên đưa thao tác ghi vào Query chỉ vì muốn gọi method thuận tiện. Việc phân biệt Query và Mutation giúp client, cache và hệ thống bảo mật hiểu đúng ý nghĩa của operation.

Query có thể ghi log, đo metrics hoặc đọc dữ liệu từ nguồn ngoài. Tuy nhiên, các hoạt động này không nên làm thay đổi trạng thái nghiệp vụ mà client không mong đợi.

## 9. Xử lý trường hợp không tìm thấy dữ liệu

Với schema:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

field `book` nullable. Nếu service cung cấp một phương thức trả về `Optional<Book>`, resolver có thể chuyển kết quả không tìm thấy thành null:

~~~java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findOptionalById(id).orElse(null);
}
~~~

Trong ví dụ này, `findOptionalById` có kiểu trả về `Optional<Book>`. Nếu service trả trực tiếp `Book` như ví dụ trước, controller có thể trả kết quả đó mà không cần gọi `orElse`.

Response khi không tìm thấy:

~~~json
{
    "data": {
        "book": null
    }
}
~~~

Nếu schema khai báo `Book!`, không thể trả null một cách bình thường. Khi không tìm thấy, cần chọn cách biểu diễn phù hợp với hợp đồng API, chẳng hạn trả lỗi GraphQL qua exception handler hoặc thiết kế một kiểu kết quả có trạng thái rõ ràng.

Không nên tự ý đổi nullability của schema chỉ để che một lỗi dữ liệu. Quyết định nullable hay non-null phải dựa trên ngữ nghĩa nghiệp vụ và cách client cần xử lý trường hợp không có kết quả.

## 10. Xử lý exception từ Query resolver

Khi service hoặc repository phát sinh exception, GraphQL engine ghi nhận lỗi trong phần `errors` của response. Có thể dùng cơ chế exception resolver của Spring for GraphQL để chuyển exception thành GraphQL error có thông tin phù hợp.

Ví dụ dùng `@GraphQlExceptionHandler` trong controller advice:

~~~java
@ControllerAdvice
public class GraphQlErrorHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(BookNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .message("Không tìm thấy sách")
                .errorType(ErrorType.NOT_FOUND)
                .build();
    }
}
~~~

Ví dụ này minh họa việc ánh xạ exception nghiệp vụ sang GraphQL error. Trong dự án thật, cần import các API GraphQL/Spring tương ứng và chọn error type, extension hoặc mã lỗi theo quy ước của ứng dụng.

Không trả stack trace, SQL, tên bảng hoặc thông tin nội bộ trong message cho client. Log chi tiết ở server với correlation ID phù hợp; response chỉ nên chứa thông tin client cần để xử lý.

Cũng cần phân biệt lỗi không tìm thấy dữ liệu với lỗi hệ thống. Không nên chuyển mọi exception thành NOT_FOUND vì điều đó che giấu lỗi kết nối database, timeout hoặc bug trong resolver.

## 11. Bảo mật cho Query field

Việc client có thể gọi một field trong schema không có nghĩa mọi người dùng đều được phép đọc dữ liệu mà field đó trả về.

Có thể bảo vệ Query bằng Spring Security method security nếu ứng dụng đã bật cấu hình tương ứng:

~~~java
@QueryMapping
@PreAuthorize("hasAuthority('BOOK_READ')")
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

Ngoài quyền truy cập chung vào field, service cần kiểm tra quyền trên tài nguyên cụ thể. Ví dụ người dùng có quyền đọc sách nhưng chỉ được xem sách thuộc tenant của mình.

Một số nguyên tắc:

- Xác thực người dùng trước khi thực thi operation theo chính sách ứng dụng.
- Kiểm tra quyền ở cấp field hoặc service khi dữ liệu có phân quyền.
- Không tin `userId`, `tenantId` hay owner ID do client truyền để quyết định quyền của chính họ.
- Không dùng việc ẩn field ở giao diện làm biện pháp bảo mật.
- Tránh trả thông tin nhạy cảm qua lỗi GraphQL.

Authorization nên dựa trên security context đáng tin cậy ở server. Nếu Query trả về object có field con nhạy cảm, cần bảo vệ field con tương ứng, kể cả khi root Query đã được phép gọi.

## 12. Kiểm thử @QueryMapping bằng GraphQlTester

Spring for GraphQL cung cấp `GraphQlTester` để kiểm thử operation mà không cần tự gửi HTTP request bằng tay.

Ví dụ test:

~~~java
@GraphQlTest(BookQueryController.class)
class BookQueryControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void returnsBookById() {
        graphQlTester.document("""
                query BookDetail($id: ID!) {
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
    }
}
~~~

Đây là ví dụ cấu trúc test slice. Nếu controller phụ thuộc BookService, hãy cung cấp mock hoặc test bean cho dependency đó theo phiên bản Spring Boot của dự án. Với `@GraphQlTest`, mục tiêu là kiểm tra schema và mapping GraphQL mà không cần khởi động toàn bộ HTTP server.

Nên kiểm thử các trường hợp:

- Query hợp lệ trả đúng dữ liệu.
- Argument được bind đúng tên và kiểu.
- Input object được bind đúng cấu trúc.
- Không tìm thấy dữ liệu trả null hoặc lỗi theo hợp đồng.
- Field non-null không nhận null.
- Exception được chuyển thành GraphQL error đúng quy ước.
- Người dùng không có quyền bị từ chối.
- Query không gọi service ngoài ý muốn khi field không được chọn.

Với kiểm thử HTTP tích hợp, dùng `@SpringBootTest` và GraphQL tester gắn với HTTP client để kiểm tra thêm endpoint, serialization, security filter và transport.

## 13. Các lỗi thường gặp khi dùng @QueryMapping

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Field không được mapping | Tên method hoặc thuộc tính `name` không khớp field SDL. | Kiểm tra `@QueryMapping(name = "...")` và `type Query`. |
| Method không được Spring phát hiện | Class thiếu `@Controller` hoặc nằm ngoài component scan. | Đăng ký controller trong package được scan. |
| Argument nhận null | Tên `@Argument` không khớp SDL hoặc client không truyền giá trị. | Đối chiếu tên argument, kiểu và variables. |
| Không bind được input object | DTO không tương thích cấu trúc input SDL. | Kiểm tra tên field, kiểu Java và nested object. |
| Resolver trả null gây lỗi | SDL khai báo field non-null nhưng method trả null. | Điều chỉnh hợp đồng hoặc xử lý trường hợp thiếu dữ liệu đúng cách. |
| Query trả response rỗng | Operation không chọn field, mapping không đúng hoặc resolver trả null. | Kiểm tra operation, schema và kết quả service. |
| Ứng dụng báo mapping xung đột | Cùng field được đăng ký qua nhiều controller hoặc runtime wiring. | Chỉ định một resolver cho mỗi field. |
| Query chậm | Service truy vấn dữ liệu không hiệu quả hoặc nested resolver gây N+1. | Đo thời gian, số truy vấn và cân nhắc DataLoader/batching. |
| Lỗi nội bộ bị lộ ra client | Exception message được trả trực tiếp. | Dùng exception resolver và message an toàn. |

Khi debug, kiểm tra theo thứ tự: SDL có field Query không, controller có được Spring scan không, method có mapping đúng tên không, argument có bind được không, rồi kiểm tra service và giá trị trả về. Nếu root field chạy đúng nhưng response sai ở field con, kiểm tra mapping của type con riêng biệt.

## 14. Quy trình triển khai một Query field

Khi thêm Query field mới, có thể làm theo trình tự:

1. Xác định dữ liệu cần đọc và quy tắc nghiệp vụ.
2. Khai báo field trong `type Query` với argument và return type phù hợp.
3. Chọn nullability dựa trên trường hợp dữ liệu không tồn tại.
4. Tạo hoặc sử dụng service để truy cập dữ liệu.
5. Viết controller `@Controller` và method `@QueryMapping`.
6. Bind argument bằng `@Argument`, ưu tiên tên tường minh khi cần.
7. Kiểm tra giới hạn đầu vào, quyền truy cập và xử lý exception.
8. Viết GraphQlTester cho trường hợp thành công và lỗi.
9. Kiểm tra operation qua endpoint HTTP trong test tích hợp khi cần.
10. Đo truy vấn nếu field trả về danh sách hoặc kích hoạt resolver lồng nhau.

## 15. Những điểm cần ghi nhớ

- `@QueryMapping` ánh xạ method Java vào field của root type Query.
- Annotation này là cách viết ngắn của `@SchemaMapping(typeName = "Query")`.
- Tên method mặc định là tên field; dùng `name` nếu hai tên khác nhau.
- `@Argument` bind argument từ SDL vào tham số Java; tên phải khớp với schema.
- Có thể nhận scalar, enum, input object và trả về object, list, scalar hoặc kết quả bất đồng bộ được hỗ trợ.
- Nullability trong SDL phải phù hợp với giá trị method có thể trả về.
- Controller nên gọi service thay vì chứa logic truy cập dữ liệu phức tạp.
- Query dùng để đọc dữ liệu và nên tránh side effect nghiệp vụ.
- Exception, authorization và giới hạn truy vấn cần được xử lý ở server.
- Dùng `GraphQlTester` để xác minh schema, mapping, arguments và response.

`@QueryMapping` là điểm kết nối trực tiếp giữa root Query trong GraphQL schema và logic đọc dữ liệu của ứng dụng Spring. Khi schema được thiết kế rõ, argument được bind chính xác và controller phối hợp với service hợp lý, Query field sẽ dễ phát triển, kiểm thử và bảo trì.

