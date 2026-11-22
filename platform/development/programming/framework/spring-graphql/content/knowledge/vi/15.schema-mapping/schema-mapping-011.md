# Tránh resolver lặp lại

## 1. Resolver lặp lại gây ra vấn đề gì?

Trong Spring for GraphQL, resolver là thành phần cung cấp dữ liệu cho một field trong GraphQL schema. Một ứng dụng có thể có nhiều controller và nhiều nhóm nghiệp vụ, nhưng mỗi field trong schema cần có một cách phân giải rõ ràng. Nếu nhiều phương thức cùng đăng ký xử lý một field, ứng dụng có thể gặp xung đột mapping khi khởi động. Nếu mỗi resolver tự viết lại cùng một truy vấn hoặc quy tắc nghiệp vụ, mã nguồn sẽ khó bảo trì và các API có thể trả kết quả không nhất quán.

Ví dụ, hai controller cùng khai báo mapping cho `Query.books`:

```java
@Controller
class BookQueryController {

    @QueryMapping
    public List<Book> books() {
        return bookRepository.findAll();
    }
}

@Controller
class CatalogQueryController {

    @QueryMapping
    public List<Book> books() {
        return catalogRepository.findAllBooks();
    }
}
```

Cả hai phương thức đều nhắm đến field `books` của root type `Query`. Spring for GraphQL không thể chọn tùy ý một phương thức làm resolver chính. Việc đăng ký mapping trùng có thể khiến quá trình khởi tạo GraphQL controller thất bại vì mapping không duy nhất.

Ngay cả khi tên phương thức khác nhau, hai phương thức vẫn có thể xung đột nếu chúng cùng khai báo `@SchemaMapping(typeName = "Book", field = "author")`. Điều quan trọng là cặp GraphQL type và field được ánh xạ, không phải tên class Java hoặc tên phương thức.

## 2. Quy tắc một mapping cho mỗi GraphQL field

Khi thiết kế resolver, hãy xác định rõ một nơi chịu trách nhiệm phân giải cho từng field. Với annotation mapping, có thể áp dụng các nguyên tắc sau:

- Một root field thuộc `Query` có một handler `@QueryMapping`.
- Một root field thuộc `Mutation` có một handler `@MutationMapping`.
- Một root field thuộc `Subscription` có một handler `@SubscriptionMapping`.
- Một field của object type có một handler `@SchemaMapping`, `@BatchMapping` hoặc cơ chế property fetcher phù hợp.
- Không đăng ký cùng một type/field bằng nhiều annotation controller hoặc nhiều cấu hình runtime wiring.

Ví dụ, giữ một controller làm chủ field `Query.books`:

```java
@Controller
public class BookQueryController {

    private final BookQueryService bookQueryService;

    public BookQueryController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookQueryService.findAll();
    }
}
```

Controller khác có thể cung cấp field khác hoặc gọi cùng service qua một luồng API riêng. Không cần tạo một resolver thứ hai cho cùng field chỉ vì một màn hình hoặc một nhóm nghiệp vụ khác muốn sử dụng dữ liệu tương tự.

## 3. Khai báo mapping tường minh để dễ nhận diện

Spring for GraphQL có thể suy ra tên field từ tên phương thức và type từ ngữ cảnh phương thức. Cách suy luận này tiện cho ví dụ nhỏ, nhưng khi dự án có nhiều controller, nên khai báo `typeName` và `field` tường minh ở những mapping quan trọng.

Ví dụ SDL:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

Resolver:

```java
@Controller
public class BookController {

    private final BookQueryService bookQueryService;

    public BookController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @QueryMapping(name = "book")
    public Book findBook(@Argument("id") String id) {
        return bookQueryService.findById(id).orElse(null);
    }
}
```

Với field lồng nhau, dùng `@SchemaMapping` để nêu rõ type và field:

```java
@Controller
public class BookAuthorController {

    private final AuthorQueryService authorQueryService;

    public BookAuthorController(AuthorQueryService authorQueryService) {
        this.authorQueryService = authorQueryService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorQueryService.findById(book.authorId()).orElse(null);
    }
}
```

`@QueryMapping` là dạng chuyên biệt cho root `Query`; `@SchemaMapping` có thể ánh xạ field của bất kỳ object type nào. Việc ghi rõ type và field giúp reviewer nhìn thấy ngay phương thức đang sở hữu mapping nào.

## 4. Tách logic dùng chung vào service

Hai resolver có thể cần cùng một quy tắc nghiệp vụ nhưng không nên sao chép truy vấn hoặc gọi trực tiếp controller của nhau. Hãy đưa logic dùng chung vào service hoặc domain component, sau đó để mỗi resolver chuyển tiếp đến thành phần đó.

Ví dụ, cả REST API và GraphQL API đều cần tra cứu sách:

```java
@Service
public class BookQueryService {

    private final BookRepository bookRepository;

    public BookQueryService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public Optional<Book> findById(String id) {
        return bookRepository.findById(id);
    }

    public List<Book> findByAuthorId(String authorId) {
        return bookRepository.findByAuthorId(authorId);
    }
}
```

GraphQL resolver:

```java
@Controller
public class BookGraphQlController {

    private final BookQueryService bookQueryService;

    public BookGraphQlController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookQueryService.findById(id).orElse(null);
    }
}
```

REST controller có thể dùng cùng service:

```java
@RestController
@RequestMapping("/api/books")
public class BookRestController {

    private final BookQueryService bookQueryService;

    public BookRestController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @GetMapping("/{id}")
    public Book findById(@PathVariable String id) {
        return bookQueryService.findById(id).orElseThrow();
    }
}
```

Như vậy, quy tắc truy cập dữ liệu được dùng lại mà mỗi giao thức vẫn có controller riêng. Không gọi một controller từ controller khác; controller là lớp tiếp nhận request, còn service mới là nơi chia sẻ hành vi nghiệp vụ.

## 5. Nhiều field cần cùng một nghiệp vụ

Có trường hợp hai field GraphQL khác nhau cùng cần một loại dữ liệu. Ví dụ `Book.author` và `Review.author` đều cần tra cứu tác giả. Đây không phải lý do để đăng ký hai resolver cho cùng một field; đây là hai field khác nhau có thể gọi cùng service.

SDL:

```graphql
type Book {
    id: ID!
    authorId: ID!
    author: Author
}

type Review {
    id: ID!
    authorId: ID!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

Hai mapping tường minh:

```java
@Controller
public class AuthorFieldController {

    private final AuthorQueryService authorQueryService;

    public AuthorFieldController(AuthorQueryService authorQueryService) {
        this.authorQueryService = authorQueryService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author bookAuthor(Book book) {
        return authorQueryService.findById(book.authorId()).orElse(null);
    }

    @SchemaMapping(typeName = "Review", field = "author")
    public Author reviewAuthor(Review review) {
        return authorQueryService.findById(review.authorId()).orElse(null);
    }
}
```

Hai phương thức ánh xạ hai cặp type/field khác nhau, nhưng cùng dùng `AuthorQueryService`. Đây là cách tái sử dụng logic phù hợp: chia sẻ nghiệp vụ và truy cập dữ liệu, đồng thời giữ mapping rõ ràng theo schema.

Nếu hai field thực sự có cùng ngữ nghĩa và có một kiểu cha chung phù hợp, có thể cân nhắc interface trong schema. Tuy nhiên, chỉ tạo interface để giảm vài dòng resolver thường không đáng giá nếu nó làm hợp đồng GraphQL khó hiểu hơn.

## 6. Không tạo resolver cho field đã có thể đọc từ object

Không phải field nào cũng cần một phương thức resolver riêng. GraphQL Java có thể dùng property data fetcher để đọc giá trị từ object nguồn, thông qua getter, property hoặc accessor phù hợp.

Ví dụ Java record:

```java
public record Book(
    String id,
    String title,
    String authorName) {
}
```

Schema:

```graphql
type Book {
    id: ID!
    title: String!
    authorName: String!
}
```

Nếu resolver của `Query.book` trả về một `Book` đã có đủ các thuộc tính này, Spring for GraphQL/GraphQL Java có thể đọc `id`, `title` và `authorName` từ object mà không cần viết ba phương thức `@SchemaMapping` riêng.

Chỉ thêm resolver khi field cần xử lý bổ sung, ví dụ tải quan hệ, áp dụng quyền truy cập, tính toán giá trị hoặc gọi một service. Tránh viết resolver chỉ để trả lại đúng một property đã có sẵn nếu không có yêu cầu nghiệp vụ bổ sung.

Không nên đưa dữ liệu nhạy cảm vào object nguồn với giả định rằng client không thể truy cập. Nếu field không được phép công bố, hãy thiết kế schema và authorization phù hợp; property data fetcher có thể đọc được thuộc tính nếu field đó được expose.

## 7. Tránh N+1 bằng `@BatchMapping`

Một resolver không bị trùng vẫn có thể gây vấn đề hiệu năng. Ví dụ query lấy 30 quyển sách và mỗi field `Book.author` gọi repository một lần sẽ tạo ra một truy vấn lấy sách cộng nhiều truy vấn lấy tác giả. Đây là vấn đề N+1.

`@BatchMapping` cho phép Spring for GraphQL gom nhiều source object của cùng một field thành một lần xử lý batch. Ví dụ:

```java
@Controller
public class BookBatchController {

    private final AuthorQueryService authorQueryService;

    public BookBatchController(AuthorQueryService authorQueryService) {
        this.authorQueryService = authorQueryService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        List<String> authorIds = books.stream()
            .map(Book::authorId)
            .distinct()
            .toList();

        Map<String, Author> authorsById =
            authorQueryService.findAllByIds(authorIds);

        return books.stream()
            .filter(book -> authorsById.containsKey(book.authorId()))
            .collect(Collectors.toMap(
                Function.identity(),
                book -> authorsById.get(book.authorId())
            ));
    }
}
```

`@BatchMapping` là cơ chế ánh xạ field theo batch và được Spring tích hợp với DataLoader. Phương thức nhận danh sách source object và trả về map từ từng source object sang giá trị field tương ứng. `AuthorQueryService.findAllByIds` là phương thức batch do ứng dụng cung cấp.

Trong ví dụ, sách không tìm thấy tác giả sẽ không có entry trong map; giá trị field tương ứng được xử lý như không có kết quả. Nếu cần phân biệt rõ tác giả không tồn tại với trường hợp dữ liệu bị thiếu, hãy định nghĩa chính sách lỗi hoặc giá trị null phù hợp với nullability trong SDL.

Không đăng ký thêm `@SchemaMapping(typeName = "Book", field = "author")` song song với `@BatchMapping` cho cùng field. `@BatchMapping` đã cung cấp data fetcher cho mapping đó. Hai cơ chế cùng đăng ký một field có thể gây xung đột.

## 8. Khi cần DataLoader dùng chung

Nếu cần kiểm soát batch loading rõ hơn hoặc chia sẻ một loader giữa nhiều resolver, có thể đăng ký DataLoader qua `BatchLoaderRegistry` rồi gọi loader từ `@SchemaMapping`.

Đăng ký batch loader trong Spring:

```java
@Configuration
public class DataLoaderConfig {

    public DataLoaderConfig(BatchLoaderRegistry registry,
                            AuthorQueryService authorQueryService) {
        registry.forTypePair(String.class, Author.class)
            .registerMappedBatchLoader((authorIds, environment) ->
                Mono.just(authorQueryService.findAllByIds(authorIds))
            );
    }
}
```

Resolver dùng loader:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<String, Author> authorLoader) {
    return authorLoader.load(book.authorId());
}
```

Spring for GraphQL hỗ trợ inject DataLoader theo tên hoặc kiểu phù hợp vào resolver method. Ví dụ này giả định loader được đăng ký với key type `String` và value type `Author`; cần bảo đảm registration và tham số resolver khớp nhau. Với `registerMappedBatchLoader`, kết quả là map theo khóa nên không phụ thuộc thứ tự của danh sách kết quả như batch loader trả list.

DataLoader được quản lý theo GraphQL execution/request context, giúp gom các lần gọi trong một operation. Không nên tự tạo một DataLoader singleton có cache dùng chung giữa người dùng, vì dữ liệu có thể phụ thuộc tenant hoặc quyền truy cập.

Chọn `@BatchMapping` khi batch chỉ phục vụ một field và muốn cấu hình ngắn gọn. Chọn `BatchLoaderRegistry` khi cần tái sử dụng loader từ nhiều resolver hoặc cần kiểm soát batch loading riêng.

## 9. Tránh đăng ký trùng giữa annotation và RuntimeWiringConfigurer

Spring for GraphQL cho phép đăng ký field resolver bằng annotation controller hoặc `RuntimeWiringConfigurer`. Hai cơ chế có thể cùng tồn tại trong một ứng dụng, nhưng không nên cùng sở hữu một cặp type/field.

Ví dụ xung đột:

```java
@Controller
class BookController {

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id).orElse(null);
    }
}
```

```java
@Bean
RuntimeWiringConfigurer duplicateBookFetcher(BookService bookService) {
    return wiring -> wiring.type(
        "Query",
        type -> type.dataFetcher("book", environment ->
            bookService.findById(environment.getArgument("id")).orElse(null)
        )
    );
}
```

Cả hai cùng đăng ký `Query.book`. Hãy chọn một cơ chế làm chủ field. Nếu muốn dùng annotation controller, bỏ data fetcher thủ công; nếu muốn dùng programmatic wiring, bỏ mapping annotation tương ứng.

`RuntimeWiringConfigurer` vẫn hữu ích cho custom scalar, `TypeResolver` hoặc cấu hình runtime khác không trùng với field controller. Có thể dùng nhiều configurer cho những trách nhiệm khác nhau, miễn là không đăng ký chồng chéo cùng một field.

## 10. Alias và fragment không tạo resolver mới

Một số trường hợp trông giống việc gọi field nhiều lần nhưng không phải mapping trùng.

Alias cho phép client đặt tên response key khác nhau khi gọi cùng field:

```graphql
query CompareBooks($firstId: ID!, $secondId: ID!) {
    first: book(id: $firstId) {
        id
        title
    }
    second: book(id: $secondId) {
        id
        title
    }
}
```

`first` và `second` là alias trong operation. Cả hai vẫn gọi field schema `Query.book`, vì vậy không cần hai resolver khác nhau.

Fragment cũng chỉ tái sử dụng selection set:

```graphql
fragment BookSummary on Book {
    id
    title
}

query BookCatalog {
    books {
        ...BookSummary
    }
}
```

`BookSummary` không phải field và không cần resolver. GraphQL mở rộng fragment khi thực thi operation rồi phân giải các field thực tế trong schema.

## 11. Quy ước tổ chức controller và service

Khi module có nhiều type, có thể tổ chức controller theo domain hoặc theo nhóm field. Điều quan trọng là mỗi mapping có một chủ sở hữu rõ ràng và logic nghiệp vụ không bị sao chép.

Ví dụ cấu trúc:

```text
graphql/
├── BookQueryController.java
├── BookFieldController.java
├── AuthorFieldController.java
└── OrderQueryController.java

application/
├── BookQueryService.java
├── AuthorQueryService.java
└── OrderQueryService.java
```

- `BookQueryController` sở hữu root query liên quan đến sách.
- `BookFieldController` sở hữu field lồng nhau của `Book`.
- `AuthorFieldController` sở hữu field lồng nhau của `Author`.
- Service chứa logic truy vấn hoặc nghiệp vụ có thể được nhiều resolver dùng chung.

Không cần tách controller chỉ để mỗi file có ít phương thức. Nếu một controller vẫn rõ trách nhiệm và không có mapping trùng, giữ các field liên quan cùng nhau có thể dễ theo dõi hơn. Hãy ưu tiên ranh giới nghiệp vụ và ownership của GraphQL field.

## 12. Kiểm thử để phát hiện resolver trùng và hành vi không nhất quán

Kiểm thử khởi tạo Spring context giúp phát hiện lỗi đăng ký mapping trước khi ứng dụng nhận traffic. Nếu có hai handler cùng sở hữu một field, context có thể thất bại ngay khi Spring for GraphQL phát hiện mapping xung đột.

Sau khi context khởi tạo thành công, dùng `GraphQlTester` để kiểm tra operation thực tế:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class BookMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void resolvesBookAndAuthorFields() {
        graphQlTester.document("""
            query {
                book(id: "book-42") {
                    id
                    title
                    author {
                        id
                        name
                    }
                }
            }
            """)
            .execute()
            .path("book.author.name")
            .entity(String.class)
            .isEqualTo("Nguyen An");
    }
}
```

Ví dụ giả định test context có fixture hoặc mock service trả về sách và tác giả tương ứng. Nên bổ sung kiểm thử để xác nhận:

- Mỗi field được phân giải đúng một lần theo mapping dự kiến.
- Các resolver dùng chung service trả kết quả nhất quán.
- Field property đơn giản hoạt động mà không cần resolver thừa.
- Batch mapping gom nhiều source object và trả đúng giá trị cho từng object.
- Field không có dữ liệu tuân thủ nullability trong schema.
- Operation alias hoặc fragment vẫn gọi đúng field mapping.
- Ứng dụng khởi động thành công với toàn bộ controller và runtime configurer.

Khi kiểm tra hiệu năng, đo số lần gọi repository hoặc service trong một operation có nhiều parent object. Một test chỉ xác nhận response đúng chưa đủ chứng minh N+1 đã được xử lý.

## 13. Lỗi thường gặp khi tránh resolver lặp lại

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Ứng dụng lỗi khi khởi động | Hai controller cùng map một type/field | Tìm các annotation mapping có cùng cặp type và field, giữ một handler |
| Field có cả `@SchemaMapping` và `@BatchMapping` | Hai cơ chế cùng đăng ký một field | Chọn một mapping; dùng `@BatchMapping` nếu cần batch |
| Annotation và RuntimeWiringConfigurer cùng map field | Resolver được đăng ký ở hai nơi | Chọn annotation hoặc programmatic fetcher cho field đó |
| Hai resolver cùng logic nhưng kết quả khác nhau | Sao chép truy vấn hoặc quy tắc nghiệp vụ | Đưa logic dùng chung vào service/domain layer |
| Nhiều phương thức Java cùng tên gây khó đọc | Dựa vào suy luận type/field trong controller lớn | Khai báo `typeName` và `field` tường minh |
| Viết resolver cho mọi property | Không tận dụng property data fetcher | Chỉ viết mapping cho field cần logic riêng |
| Vẫn có N+1 dù chỉ có một resolver | Resolver chạy một lần cho mỗi source object | Dùng `@BatchMapping` hoặc DataLoader |
| Controller gọi controller khác | Chia sẻ logic ở sai tầng | Tách service hoặc domain component dùng chung |
| DataLoader trả dữ liệu nhầm người dùng | Cache được chia sẻ ngoài request hoặc thiếu tenant context | Dùng loader theo execution và kiểm tra quyền trong batch service |

## 14. Checklist trước khi hoàn thiện schema mapping

- [ ] Mỗi cặp GraphQL type/field có một cơ chế phân giải rõ ràng.
- [ ] Không có hai `@QueryMapping`, `@MutationMapping` hoặc `@SchemaMapping` cùng đăng ký một field.
- [ ] Không đăng ký cùng field bằng annotation và `RuntimeWiringConfigurer`.
- [ ] `@BatchMapping` được dùng thay cho mapping đơn lẻ khi cần batch cùng field.
- [ ] Mapping quan trọng khai báo `typeName` và `field` tường minh.
- [ ] Logic nghiệp vụ dùng chung nằm trong service hoặc domain layer.
- [ ] Resolver không gọi controller khác.
- [ ] Property data fetcher được tận dụng cho field có thể đọc trực tiếp từ object.
- [ ] Alias và fragment được hiểu đúng là cấu trúc operation, không phải resolver mới.
- [ ] Có kiểm thử khởi tạo context và operation bằng `GraphQlTester`.
- [ ] Có đo số lần gọi backend để phát hiện N+1.

## Kết luận

Tránh resolver lặp lại bắt đầu từ việc quản lý rõ mapping giữa GraphQL type và field. Mỗi field nên có một nơi chịu trách nhiệm phân giải; không đăng ký cùng field ở nhiều controller hoặc đồng thời qua annotation và `RuntimeWiringConfigurer`. Khi nhiều field cần cùng logic, hãy chia sẻ service hoặc domain component thay vì sao chép code hoặc gọi controller lẫn nhau.

Trong Spring for GraphQL, `@QueryMapping` phù hợp với root query, `@SchemaMapping` dành cho field của object type và `@BatchMapping` hỗ trợ gom việc tải field theo batch. Với property đã có sẵn trên object, hãy tận dụng property data fetcher để tránh resolver không cần thiết. Kết hợp ownership rõ ràng, service dùng chung và kiểm thử `GraphQlTester` sẽ giúp schema mapping dễ bảo trì, nhất quán và tránh xung đột khi ứng dụng mở rộng.
