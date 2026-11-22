# DataFetcher từ handler method

Trong GraphQL Java, **DataFetcher** là thành phần cung cấp giá trị cho một field khi operation được thực thi. Spring for GraphQL cho phép developer viết các method Java thông thường trong annotated controller; framework phát hiện các method đó và đăng ký một DataFetcher tương ứng cho từng field trong schema.

Cách tiếp cận này giúp code resolver gần với cấu trúc nghiệp vụ của ứng dụng. Thay vì tự tạo DataFetcher và thao tác trực tiếp với DataFetchingEnvironment cho mọi field, developer có thể dùng các annotation như **@QueryMapping**, **@MutationMapping**, **@SubscriptionMapping** và **@SchemaMapping**. Spring xử lý việc tìm method, ánh xạ argument, truyền source object và chuyển kết quả method thành kết quả GraphQL.

Bài này giải thích mối quan hệ giữa handler method và DataFetcher, quy tắc mapping, cách Spring phân giải tham số, kiểu trả về đồng bộ/bất đồng bộ, xử lý lỗi, tối ưu field resolver và kiểm thử.

## 1. DataFetcher trong GraphQL Java

Một GraphQL operation có thể chọn nhiều field. Với mỗi field cần thực thi, GraphQL Java gọi **DataFetcher** đã được đăng ký trong schema để lấy giá trị.

Ví dụ schema:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Khi client gửi:

~~~graphql
query {
  book(id: "book-01") {
    id
    title
  }
}
~~~

GraphQL Java cần một DataFetcher cho field **Query.book**. Giá trị mà DataFetcher trả về trở thành source object cho field con **Book.id** và **Book.title**. Những field con có thể được giải quyết bằng DataFetcher riêng hoặc property data fetcher mặc định.

Trong GraphQL Java thuần, có thể đăng ký DataFetcher trực tiếp:

~~~java
RuntimeWiring wiring = RuntimeWiring.newRuntimeWiring()
        .type("Query", typeWiring -> typeWiring
                .dataFetcher("book", environment -> {
                    String id = environment.getArgument("id");
                    return bookService.findById(id);
                }))
        .build();
~~~

Đoạn code này cho thấy DataFetcher nhận **DataFetchingEnvironment**, đọc argument và trả về dữ liệu. Spring for GraphQL vẫn sử dụng cơ chế DataFetcher của GraphQL Java, nhưng cho phép khai báo logic bằng handler method và để framework thực hiện phần adapter.

## 2. Annotated controller biến method thành DataFetcher

Một controller được đánh dấu bằng **@Controller**. Các method có annotation mapping của Spring for GraphQL được phát hiện và đăng ký làm DataFetcher cho field tương ứng.

Ví dụ:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

Method **book** trở thành handler cho field **Query.book**. Spring tạo DataFetcher bao quanh lời gọi method, chuyển argument GraphQL thành tham số Java, gọi method và chuyển kết quả trả về cho GraphQL Java.

Luồng xử lý khái quát:

~~~mermaid
flowchart TD
    A[GraphQL operation] --> B[GraphQL Java thực thi field]
    B --> C[DataFetcher được Spring đăng ký]
    C --> D[Annotated controller handler]
    D --> E[Phân giải tham số]
    E --> F[Gọi method Java]
    F --> G[Service / repository]
    G --> H[Kết quả method]
    H --> I[GraphQL tiếp tục resolve selection set]
    I --> J[Response]
~~~

Vì vậy, handler method không phải là một loại GraphQL field mới. Nó là cách Spring cung cấp DataFetcher cho field đã được khai báo trong SDL.

### Vai trò của AnnotatedControllerConfigurer

Trong cơ chế annotated controller, **AnnotatedControllerConfigurer** phát hiện các controller và handler method, sau đó đăng ký DataFetcher vào runtime wiring. Spring Boot thường tự cấu hình thành phần này khi ứng dụng dùng Spring for GraphQL starter.

Developer thường chỉ cần:

1. Khai báo schema SDL.
2. Đánh dấu class là **@Controller**.
3. Đánh dấu method bằng annotation mapping phù hợp.
4. Cung cấp service mà method cần gọi.

Không cần tự tạo một DataFetcher thủ công cho mỗi method được ánh xạ theo cách này.

## 3. Các annotation mapping chính

Spring for GraphQL cung cấp các annotation rút gọn cho root operation và annotation tổng quát cho field mapping:

| Annotation | Field mặc định được ánh xạ |
|---|---|
| **@QueryMapping** | Field trên root type **Query** |
| **@MutationMapping** | Field trên root type **Mutation** |
| **@SubscriptionMapping** | Field trên root type **Subscription** |
| **@SchemaMapping** | Field trên object type hoặc interface được chỉ định/suy ra |

Ví dụ SDL:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Subscription {
  bookPublished: Book!
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book book(@Argument String id) {
        // Tìm một quyển sách
        return null;
    }

    @MutationMapping
    public Book createBook(@Argument CreateBookInput input) {
        // Tạo một quyển sách
        return null;
    }

    @SubscriptionMapping
    public Flux<Book> bookPublished() {
        // Phát các sách mới được xuất bản
        return publisherOfBooks();
    }
}
~~~

**@QueryMapping** tương đương một **@SchemaMapping** trên type **Query**; **@MutationMapping** và **@SubscriptionMapping** cũng là các cách khai báo chuyên biệt cho root operation type tương ứng.

Tên method thường được dùng làm tên field nếu không chỉ định tên khác. Nếu method Java có tên khác với field trong SDL, hãy khai báo tường minh:

~~~java
@QueryMapping(name = "book")
public Book findBookById(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}
~~~

Việc đặt tên tường minh giúp code Java có thể theo quy ước nội bộ mà không làm thay đổi hợp đồng GraphQL.

## 4. @SchemaMapping cho field của object

Root mapping giải quyết các field bắt đầu từ Query, Mutation hoặc Subscription. Khi client chọn field lồng nhau trên một object, có thể dùng **@SchemaMapping**.

SDL:

~~~graphql
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
~~~

Controller:

~~~java
@Controller
public class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    public BookController(
            BookService bookService,
            AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

Khi GraphQL thực thi **Book.author**, Spring gọi method **author**. Tham số **Book book** là source object được trả về từ field cha **Query.book**.

### Suy ra typeName và field

Có thể bỏ một số thuộc tính nếu tên method và kiểu source đủ rõ:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Spring có thể suy ra:

- **typeName** từ kiểu source object **Book**.
- **field** từ tên method **author**.

Khi muốn gom các mapping của một object type trong cùng controller, có thể đặt **@SchemaMapping** ở cấp class:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
public class BookFieldController {

    @SchemaMapping
    public Author author(Book book) {
        return null;
    }

    @SchemaMapping
    public List<Review> reviews(Book book) {
        return List.of();
    }
}
~~~

Ở ví dụ này, các method được ánh xạ vào field của **Book**; tên field được suy ra từ tên method. Có thể ghi **field** tường minh khi tên Java không trùng tên SDL.

## 5. Quy tắc ánh xạ method vào field

Khi framework phát hiện một handler method, mapping cần xác định hai thông tin:

1. GraphQL type chứa field.
2. Tên field cần được xử lý.

Có thể chỉ định trực tiếp:

~~~java
@SchemaMapping(typeName = "Book", field = "publishedAt")
public Instant publicationDate(Book source) {
    return source.getPublishedAt();
}
~~~

Hoặc dùng quy ước:

~~~java
@SchemaMapping
public Instant publishedAt(Book book) {
    return book.getPublishedAt();
}
~~~

Với root operation:

~~~java
@QueryMapping
public List<Book> books() {
    return bookService.findAll();
}
~~~

Method trên được ánh xạ vào **Query.books**.

Các mapping phải khớp với type và field trong schema. Một method không có annotation mapping phù hợp không tự động trở thành GraphQL field chỉ vì tên của nó trùng với field trong SDL.

Nếu có hai handler method cùng đăng ký cho một GraphQL field, ứng dụng có thể gặp xung đột khi xây dựng runtime wiring. Hãy giữ một mapping rõ ràng cho mỗi field và dùng service method để chia sẻ logic giữa các controller nếu cần.

## 6. Phân giải tham số của handler method

Spring for GraphQL hỗ trợ nhiều kiểu tham số. Framework đọc GraphQL execution context và chuyển các giá trị phù hợp vào method.

Các tham số thường dùng:

| Tham số | Ý nghĩa |
|---|---|
| **@Argument** | Lấy một argument của GraphQL field |
| **@Arguments** | Bind toàn bộ argument thành Map hoặc object |
| Source object | Object kết quả từ field cha |
| **DataFetchingEnvironment** | Truy cập trực tiếp GraphQL execution environment |
| **@ContextValue** | Lấy giá trị từ GraphQLContext |
| **@LocalContextValue** | Lấy giá trị từ local context của field |
| **Principal** | Principal của request nếu có trong execution context |

Không cần khai báo tất cả tham số. Chỉ nhận những gì handler thực sự cần.

### @Argument

Với SDL:

~~~graphql
type Query {
  book(id: ID!, includeArchived: Boolean = false): Book
}
~~~

Handler:

~~~java
@QueryMapping
public Book book(
        @Argument("id") String bookId,
        @Argument Boolean includeArchived) {

    return bookService.findById(bookId, includeArchived);
}
~~~

Tên argument có thể chỉ định trong annotation. Nếu bỏ tên, Spring sử dụng tên tham số Java theo metadata có sẵn. Để tránh phụ thuộc vào việc compiler có giữ tên tham số hay không, nên ghi rõ tên khi mapping có thể gây nhầm lẫn.

### Bind input object

SDL:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Java record:

~~~java
public record CreateBookInput(String title, String authorId) {
}
~~~

Handler:

~~~java
@MutationMapping
public Book createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
~~~

Spring bind input object thành Java record/DTO. Cấu trúc Java cần tương thích với field trong input type; schema vẫn là hợp đồng quyết định những giá trị client được phép gửi.

### Source object

Khi resolve field con, handler thường nhận object nguồn làm tham số:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book source) {
    return authorService.findById(source.getAuthorId());
}
~~~

Tham số **Book source** không phải argument do client gửi. Nó là kết quả đã được resolve ở cấp cha. Phân biệt rõ source object với **@Argument** giúp tránh nhầm lẫn giữa dữ liệu cha và dữ liệu đầu vào của field hiện tại.

### DataFetchingEnvironment

Khi cần truy cập nhiều thông tin GraphQL ở mức thấp hơn, có thể nhận **DataFetchingEnvironment**:

~~~java
@QueryMapping
public Book book(
        @Argument String id,
        DataFetchingEnvironment environment) {

    String executionPath = environment.getExecutionStepInfo()
            .getPath()
            .toString();

    return bookService.findById(id);
}
~~~

**DataFetchingEnvironment** cung cấp arguments, source, GraphQL context, selection set, field definition và thông tin execution. Chỉ nên dùng khi thực sự cần dữ liệu ở mức GraphQL; với các tham số thông thường, annotation chuyên biệt giúp chữ ký method dễ đọc hơn.

### GraphQL context

Có thể đưa thông tin dùng chung của request vào GraphQLContext ở interceptor, sau đó lấy trong handler:

~~~java
@QueryMapping
public List<Book> books(
        @ContextValue("tenantId") String tenantId) {
    return bookService.findForTenant(tenantId);
}
~~~

**@ContextValue** lấy giá trị từ GraphQLContext. Với giá trị chỉ được truyền trong một nhánh thực thi, có thể dùng **@LocalContextValue**. Context giúp handler không phải đọc trực tiếp HTTP request hoặc phụ thuộc vào một transport cụ thể.

## 7. Kiểu trả về của handler method

Handler method có thể trả về giá trị đồng bộ hoặc kiểu bất đồng bộ/reactive được Spring for GraphQL hỗ trợ.

| Kiểu trả về | Ví dụ | Ý nghĩa |
|---|---|---|
| Object/DTO | **Book** | Một giá trị cho field |
| Collection | **List<Book>** | Danh sách giá trị |
| **CompletionStage<T>** | **CompletableFuture<Book>** | Kết quả bất đồng bộ |
| **Mono<T>** | **Mono<Book>** | Kết quả reactive đơn |
| **Publisher<T>** | **Flux<BookEvent>** | Luồng giá trị, đặc biệt hữu ích cho subscription |

Ví dụ đồng bộ:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

Ví dụ bất đồng bộ:

~~~java
@QueryMapping
public CompletableFuture<Book> book(@Argument String id) {
    return bookService.findByIdAsync(id);
}
~~~

Ví dụ với Reactor:

~~~java
@QueryMapping
public Mono<Book> book(@Argument String id) {
    return bookService.findByIdReactive(id);
}
~~~

Spring for GraphQL tích hợp với cơ chế async/reactive của Spring để chuyển kết quả method vào quá trình thực thi GraphQL. Kiểu trả về phải phù hợp với kiểu field trong schema. Ví dụ field **Book** cần một giá trị Book; field **[Book!]!** cần một collection hoặc publisher được hỗ trợ có thể tạo ra kết quả list phù hợp.

### Subscription trả về Publisher

Subscription thường phát nhiều kết quả theo thời gian. Handler có thể trả về **Flux<T>** hoặc **Publisher<T>**:

~~~graphql
type Subscription {
  bookPublished: Book!
}
~~~

~~~java
@SubscriptionMapping
public Flux<Book> bookPublished() {
    return bookEventService.bookPublished();
}
~~~

Mỗi phần tử phát ra từ publisher tạo một lần thực thi selection set của subscription và một payload gửi đến client. Khi client hủy subscription hoặc kết nối đóng, nguồn phát cần được dọn dẹp theo đúng vòng đời.

Không nên trả một publisher vô hạn cho Query hoặc Mutation chỉ vì có thể dùng kiểu reactive. Hãy chọn kiểu trả về theo semantics của field và transport.

## 8. DataFetcher từ handler method hoạt động trong runtime wiring

Spring không biến method Java thành field mới trong SDL. SDL vẫn phải khai báo field:

~~~graphql
type Query {
  books: [Book!]!
}
~~~

Handler method:

~~~java
@QueryMapping
public List<Book> books() {
    return bookService.findAll();
}
~~~

Annotated controller infrastructure đăng ký một DataFetcher cho **Query.books**. Khi GraphQL thực thi field, DataFetcher gọi handler method và trả kết quả cho GraphQL Java.

Điều này có nghĩa:

- SDL quyết định field nào tồn tại và kiểu dữ liệu của nó.
- Annotation quyết định method nào xử lý field.
- Parameter resolver chuyển dữ liệu execution thành tham số Java.
- Handler method gọi service và trả kết quả.
- GraphQL Java tiếp tục xử lý kết quả theo selection set và schema.

Nếu field được khai báo trong SDL nhưng không có annotated handler, GraphQL vẫn có thể dùng default property data fetcher tùy source object. Với root Query không có source object hữu ích, cần có DataFetcher phù hợp để trả dữ liệu.

## 9. Khi nào dùng @SchemaMapping và khi nào dùng @BatchMapping?

**@SchemaMapping** thường xử lý một source object cho mỗi lần gọi. Nếu query lấy nhiều parent object và mỗi field con truy vấn database riêng, có thể phát sinh N+1.

Ví dụ:

~~~graphql
type Query {
  books: [Book!]!
}

type Book {
  id: ID!
  author: Author!
}
~~~

Handler thông thường:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Nếu query trả về 100 Book, method có thể được gọi 100 lần. Khi cần gom tải dữ liệu, Spring for GraphQL cung cấp **@BatchMapping**:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    List<String> authorIds = books.stream()
            .map(Book::getAuthorId)
            .distinct()
            .toList();

    Map<String, Author> authors =
            authorService.findAllByIds(authorIds);

    Map<Book, Author> result = new HashMap<>();
    for (Book book : books) {
        Author author = authors.get(book.getAuthorId());
        if (author != null) {
            result.put(book, author);
        }
    }
    return result;
}
~~~

**@BatchMapping** là một cách khai báo batch loader dựa trên handler method. Framework gom source object và phân phối kết quả theo từng source. Với các trường hợp phức tạp hơn hoặc cần chia sẻ loader, có thể dùng DataLoader trực tiếp.

Không phải mọi field đều cần batch mapping. Nếu field là property có sẵn trên source object, default property data fetcher thường đủ. Dùng batch khi có chi phí tải dữ liệu theo từng source và có thể gom các lần tải thành một thao tác hiệu quả hơn.

## 10. Xử lý exception từ handler method

Nếu handler method ném exception, lỗi được chuyển vào cơ chế xử lý lỗi của GraphQL execution. Không nên để exception nội bộ hoặc stack trace xuất hiện trực tiếp trong response production.

Có thể xử lý exception tại controller bằng **@GraphQlExceptionHandler**:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(BookNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .message("Không tìm thấy sách")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
~~~

Để xử lý lỗi dùng chung cho nhiều controller, có thể kết hợp **@ControllerAdvice** và **@GraphQlExceptionHandler**, hoặc triển khai **DataFetcherExceptionResolver**.

Khi thiết kế lỗi, cần:

- Trả thông điệp phù hợp cho client.
- Dùng error classification/code nhất quán.
- Không để lộ SQL, token, stack trace hoặc chi tiết hạ tầng.
- Ghi log phía server với correlation ID nếu cần điều tra.
- Hiểu rằng GraphQL có thể trả partial data cùng errors tùy field và nullability.

## 11. Validation và bảo mật trên handler method

Handler method là một ranh giới phù hợp để nhận dữ liệu và điều phối use case, nhưng không nên dồn mọi quy tắc nghiệp vụ vào controller.

Ví dụ input:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Java:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @NotBlank String authorId) {
}
~~~

Handler:

~~~java
@MutationMapping
public Book createBook(@Argument("input") @Valid CreateBookInput input) {
    return bookService.create(input);
}
~~~

Schema kiểm tra kiểu và field bắt buộc. Bean Validation kiểm tra constraint như **@NotBlank**; service kiểm tra tác giả có tồn tại, quyền của người dùng và các quy tắc nghiệp vụ.

Có thể áp dụng method security trên handler hoặc service:

~~~java
@PreAuthorize("hasAuthority('BOOK_EDITOR')")
@MutationMapping
public Book createBook(@Argument("input") @Valid CreateBookInput input) {
    return bookService.create(input);
}
~~~

Ứng dụng phải bật và cấu hình method security tương ứng. Với nghiệp vụ được gọi từ nhiều adapter, đặt authorization cuối cùng trong service giúp chính sách được áp dụng nhất quán.

Không nên lấy tenant hoặc role từ argument do client tự gửi rồi tin trực tiếp. Hãy dùng principal đã xác thực hoặc context được server tạo ra.

## 12. Tổ chức controller và service

Một controller nên tập trung vào mapping và chuyển tiếp dữ liệu cần thiết. Nghiệp vụ nên nằm trong service:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public List<Book> books(@Argument Integer first) {
        return bookService.findFirst(first);
    }
}
~~~

Một controller có thể gom các handler liên quan, nhưng không cần biến nó thành nơi chứa toàn bộ logic đọc/ghi dữ liệu. Có thể chia controller theo domain hoặc nhóm operation để dễ tìm mapping và kiểm thử.

Không nên inject repository vào mọi controller nếu service đã encapsulate quy tắc nghiệp vụ. Controller nên chịu trách nhiệm chuyển request GraphQL thành lời gọi use case và trả kết quả phù hợp schema.

## 13. Những lỗi mapping thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Field không được resolve | Thiếu annotation mapping hoặc sai type/field name | Kiểm tra SDL và annotation |
| Handler không được phát hiện | Class không phải Spring bean hoặc thiếu **@Controller** | Đăng ký controller trong application context |
| Method map vào sai field | Dựa vào tên mặc định không đúng | Chỉ định **typeName** và **field** tường minh |
| Argument Java nhận null | Tên argument không khớp hoặc client không truyền | Kiểm tra SDL, operation và **@Argument** |
| Source object sai kiểu | Mapping đặt trên type khác hoặc resolver trả object không đúng | Kiểm tra kiểu output của field cha |
| Có nhiều handler cho một field | Mapping bị trùng | Giữ một handler mapping cho field |
| Query tạo nhiều truy vấn database | Resolver field con gọi service từng source | Dùng **@BatchMapping** hoặc DataLoader |
| Subscription không phát event | Handler không trả Publisher phù hợp hoặc nguồn không phát | Kiểm tra publisher và lifecycle |
| Exception làm lộ thông tin nội bộ | Chưa chuẩn hóa GraphQL error | Dùng exception handler hoặc resolver |
| Property fetcher bị ghi đè ngoài ý muốn | Có mapping tường minh cho field vốn đọc từ property | Kiểm tra field cần custom resolver hay không |

## 14. Kiểm thử annotated handler method

Spring for GraphQL cung cấp **GraphQlTester** và các biến thể kiểm thử theo transport. Có thể kiểm tra handler ở mức GraphQL mà không cần gửi request HTTP thực:

~~~java
@SpringBootTest
class BookQueryControllerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldResolveBook() {
        graphQlTester.document("""
                query FindBook($id: ID!) {
                    book(id: $id) {
                        id
                        title
                    }
                }
                """)
            .variable("id", "book-01")
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL");
    }
}
~~~

Nên kiểm tra:

1. Handler được đăng ký đúng với field trong SDL.
2. Argument và input object được bind đúng.
3. Source object được truyền đúng cho field mapping.
4. Kết quả method phù hợp với kiểu trả về của schema.
5. Async/reactive result được xử lý đúng.
6. Exception được ánh xạ thành GraphQL error mong muốn.
7. Field resolver không truy cập dữ liệu ngoài quyền.
8. Batch mapping giảm số lần tải dữ liệu và giữ đúng quan hệ source-result.
9. Subscription phát event và cleanup khi client hủy.
10. Mapping trùng hoặc sai schema được phát hiện khi khởi tạo application context.

Nếu mục tiêu là kiểm tra HTTP headers, endpoint path, serialization hoặc security filter của web stack, hãy bổ sung test qua **HttpGraphQlTester** hoặc test client phù hợp. **GraphQlTester** ở mức execution không thay thế hoàn toàn kiểm thử transport.

## 15. Quy trình tạo DataFetcher bằng handler method

Khi triển khai một field mới:

1. Khai báo field và kiểu dữ liệu trong SDL.
2. Chọn root mapping (**@QueryMapping**, **@MutationMapping**, **@SubscriptionMapping**) hoặc **@SchemaMapping**.
3. Đặt handler trong class Spring **@Controller**.
4. Chỉ định **typeName**/**field** khi không muốn dùng tên mặc định.
5. Khai báo tham số bằng **@Argument**, source object, context hoặc execution environment phù hợp.
6. Gọi service để thực hiện use case.
7. Chọn kiểu trả về đồng bộ, async hoặc reactive theo semantics của field.
8. Xử lý validation, authorization và exception ở đúng lớp.
9. Xem xét N+1 và dùng **@BatchMapping**/DataLoader khi có thể gom tải.
10. Viết GraphQlTester để xác nhận mapping và kết quả.

Annotated controller giúp Spring for GraphQL chuyển handler method thành DataFetcher mà không bắt developer tự quản lý toàn bộ GraphQL Java wiring. SDL vẫn xác định hợp đồng; annotation nối field với method; parameter resolver cung cấp argument, source và context; method gọi service và trả kết quả để GraphQL tiếp tục thực thi selection set. Giữ controller tập trung vào mapping, đặt nghiệp vụ trong service và kiểm thử ở mức GraphQL sẽ giúp resolver dễ đọc, dễ bảo trì và nhất quán hơn.
