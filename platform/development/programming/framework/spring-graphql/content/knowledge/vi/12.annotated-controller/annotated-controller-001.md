# @Controller trong Spring GraphQL

Spring for GraphQL cho phép ánh xạ các field trong GraphQL schema vào phương thức Java bằng annotation. Một bean được đánh dấu **@Controller** là nơi thường đặt những phương thức xử lý Query, Mutation, Subscription và các field của object type. Spring phát hiện bean này trong quá trình component scanning, sau đó đăng ký các phương thức có annotation GraphQL để chúng trở thành resolver của schema.

Controller là lớp kết nối hợp đồng GraphQL với tầng nghiệp vụ. Nó nhận argument từ operation, gọi service phù hợp và trả kết quả cho GraphQL runtime. Controller không cần tự phân tích chuỗi query hoặc tạo JSON response; GraphQL Java thực thi operation và tạo response dựa trên schema.

## Vai trò của @Controller

Trong Spring Framework, **@Controller** là một stereotype annotation thuộc nhóm component. Nó đánh dấu một lớp là thành phần do Spring quản lý và cho phép component scanning phát hiện lớp đó để tạo bean. Spring for GraphQL sử dụng các bean controller đã được quản lý để tìm những phương thức có annotation như:

- **@QueryMapping**: xử lý field trên Query root.
- **@MutationMapping**: xử lý field trên Mutation root.
- **@SubscriptionMapping**: xử lý field trên Subscription root.
- **@SchemaMapping**: xử lý field của một object type cụ thể.
- **@BatchMapping**: phân giải một field cho nhiều source object theo lô.

Ví dụ, controller có thể khai báo phương thức xử lý field book:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

Khi client gửi query chọn field book, Spring for GraphQL gọi phương thức tương ứng. Giá trị trả về được GraphQL runtime tiếp tục phân giải theo các field mà client yêu cầu.

**@Controller không phải annotation định nghĩa HTTP endpoint.** Nó không thay thế @PostMapping hoặc @GetMapping trong ứng dụng MVC. Với GraphQL, transport handler tiếp nhận request tại endpoint GraphQL, còn các annotation trên controller ánh xạ operation hoặc field bên trong schema.

## @Controller khác gì @RestController?

@Controller và @RestController đều là stereotype của Spring MVC, nhưng mục đích sử dụng thường khác nhau:

| Annotation | Mục đích thường gặp |
| --- | --- |
| **@Controller** | Khai báo Spring MVC controller hoặc annotated GraphQL controller |
| **@RestController** | Khai báo REST controller, kết hợp @Controller và @ResponseBody |

Spring for GraphQL tìm các bean controller có phương thức gắn annotation GraphQL. Vì vậy, hãy dùng @Controller cho annotated GraphQL controller. @RestController không phải lựa chọn cần thiết cho GraphQL resolver; @ResponseBody cũng không dùng để định dạng response GraphQL. GraphQL runtime tự xây dựng response theo schema.

Một ứng dụng có thể đồng thời cung cấp REST API và GraphQL API. Khi đó, REST controller xử lý HTTP mapping như @GetMapping, còn GraphQL controller xử lý field bằng @QueryMapping hoặc @SchemaMapping. Hai loại controller có thể cùng tồn tại trong một Spring application context.

## Component scanning và vị trí controller

Spring Boot thường bắt đầu component scanning từ package chứa lớp gắn @SpringBootApplication và quét các package con. Vì vậy, nên đặt GraphQL controller bên dưới package gốc của ứng dụng:

~~~text
com.example.catalog
├── CatalogApplication.java
├── graphql
│   ├── BookController.java
│   └── AuthorController.java
├── service
│   ├── BookService.java
│   └── AuthorService.java
└── repository
    └── BookRepository.java
~~~

Ví dụ lớp khởi động:

~~~java
@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Nếu controller nằm ngoài package được quét, Spring không tạo bean cho lớp đó. Khi ấy các phương thức resolver không được đăng ký, và ứng dụng có thể báo lỗi không tìm thấy data fetcher cho field hoặc trả về hành vi mặc định ngoài mong đợi.

Có thể cấu hình phạm vi component scanning bằng @ComponentScan khi ứng dụng có cấu trúc package đặc biệt. Tuy nhiên, trước tiên hãy kiểm tra package của lớp @SpringBootApplication và vị trí controller để tránh cấu hình quét rộng không cần thiết.

## Khai báo schema và controller tương ứng

Giả sử API quản lý sách có schema:

~~~graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
  publishedYear: Int
}

input CreateBookInput {
  title: String!
  publishedYear: Int
}
~~~

Các field book và books thuộc Query; createBook thuộc Mutation. Object Book mô tả dữ liệu trả về, còn CreateBookInput mô tả dữ liệu client gửi lên.

Controller có thể triển khai như sau:

~~~java
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

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }

    @MutationMapping
    public Book createBook(@Argument CreateBookInput input) {
        return bookService.create(input);
    }
}
~~~

Spring quản lý BookController như một bean. Constructor injection cung cấp BookService; các annotation GraphQL xác định phương thức nào xử lý field nào. Khi client gửi operation hợp lệ, GraphQL Java tìm data fetcher đã được Spring đăng ký và gọi phương thức controller tương ứng.

## @QueryMapping

**@QueryMapping** ánh xạ phương thức vào field thuộc Query root. Nếu không truyền tên trong annotation, Spring dùng tên phương thức làm tên field:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

Phương thức trên xử lý field book trong schema. Có thể chỉ định tên field tường minh khi tên phương thức Java khác tên schema:

~~~java
@QueryMapping(name = "featuredBooks")
public List<Book> findFeatured() {
    return bookService.findFeatured();
}
~~~

Với cách khai báo này, field featuredBooks trong Query được ánh xạ tới phương thức findFeatured. Tên field trong SDL vẫn phải tồn tại và kiểu trả về của phương thức cần tương thích với kiểu đã khai báo.

## @MutationMapping và @SubscriptionMapping

**@MutationMapping** ánh xạ phương thức vào field thuộc Mutation root. Ví dụ:

~~~java
@MutationMapping
public Book renameBook(
        @Argument String id,
        @Argument String title) {
    return bookService.rename(id, title);
}
~~~

Mutation nên gọi service để thực hiện quy tắc nghiệp vụ, validation và thay đổi dữ liệu. Không nên đặt logic cập nhật phức tạp trực tiếp trong controller.

**@SubscriptionMapping** ánh xạ phương thức vào field thuộc Subscription root. Phương thức subscription thường trả về một publisher reactive như Flux:

~~~java
@SubscriptionMapping
public Flux<Book> bookCreated() {
    return bookEventService.bookCreated();
}
~~~

Schema tương ứng:

~~~graphql
type Subscription {
  bookCreated: Book!
}
~~~

Để client nhận được sự kiện, ứng dụng còn phải cấu hình transport hỗ trợ subscription, chẳng hạn WebSocket. Chỉ khai báo annotation hoặc root type Subscription không tự tạo kết nối truyền sự kiện.

## @SchemaMapping cho field của object type

Một GraphQL object có thể chứa field liên kết tới object khác. Khi field cần gọi service hoặc truy vấn nguồn dữ liệu, dùng **@SchemaMapping**:

~~~graphql
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

Resolver của field author:

~~~java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
~~~

Tham số Book là source object, tức object cha mà GraphQL đang phân giải. Spring truyền object đó vào phương thức để resolver có thể lấy authorId. Annotation chỉ rõ kiểu nguồn Book và field author.

Nếu không chỉ định typeName hoặc field, Spring có thể suy luận tên từ kiểu tham số nguồn và tên phương thức. Ví dụ phương thức author(Book book) thường được hiểu là field author của kiểu Book. Khi schema lớn hoặc tên Java không trùng tên SDL, khai báo tường minh giúp mapping dễ đọc và ít nhầm lẫn hơn.

Nếu Java object có property tương ứng với field trong schema, GraphQL có thể đọc giá trị bằng property access mặc định mà không cần viết @SchemaMapping. Hãy tạo resolver riêng khi field cần truy vấn dữ liệu, gọi service, áp dụng logic hoặc lấy giá trị từ nguồn khác.

## Nhận argument bằng @Argument

GraphQL field có thể nhận argument. Annotation **@Argument** lấy giá trị argument từ operation và chuyển đổi sang kiểu Java:

~~~graphql
type Query {
  book(id: ID!): Book
  searchBooks(keyword: String!, limit: Int = 10): [Book!]!
}
~~~

~~~java
@QueryMapping
public Book book(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}

@QueryMapping
public List<Book> searchBooks(
        @Argument String keyword,
        @Argument Integer limit) {
    return bookService.search(keyword, limit);
}
~~~

Tên trong @Argument phải khớp với tên argument trong SDL. Có thể bỏ tên khi tên tham số Java được giữ lại và Spring có thể suy luận chính xác. Khi tên Java khác tên schema, hãy ghi tên rõ ràng như @Argument("id").

Với input object, có thể nhận cả object bằng một tham số:

~~~java
public record CreateBookInput(String title, Integer publishedYear) {
}

@MutationMapping
public Book createBook(@Argument CreateBookInput input) {
    return bookService.create(input);
}
~~~

Spring chuyển input object thành kiểu Java tương ứng thông qua cơ chế conversion và binding. Cấu trúc Java cần tương thích với field và kiểu trong SDL. Nếu input chứa dữ liệu phức tạp, nên dùng DTO hoặc record riêng thay vì bind trực tiếp vào persistence entity.

## Các tham số đặc biệt trong annotated controller

Ngoài argument và source object, phương thức resolver có thể cần context thực thi. Spring for GraphQL hỗ trợ một số kiểu tham số đặc biệt, ví dụ:

| Tham số | Cách nhận | Công dụng |
| --- | --- | --- |
| Argument | @Argument | Lấy argument của field |
| Source object | Tham số object cha, thường là tham số đầu vào không gắn annotation | Phân giải field lồng nhau |
| GraphQLContext | Kiểu GraphQLContext | Đọc dữ liệu context của operation |
| Context value | @ContextValue | Lấy một giá trị theo key từ GraphQLContext |
| Local context value | @LocalContextValue | Lấy giá trị từ local context được truyền giữa các field |
| DataFetchingEnvironment | Tham số DataFetchingEnvironment | Truy cập thông tin thực thi field hiện tại |
| Principal | Tham số Principal | Truy cập principal đã được xác thực nếu có |

Ví dụ lấy một giá trị từ GraphQL context:

~~~java
@QueryMapping
public List<Book> myBooks(@ContextValue("tenantId") String tenantId) {
    return bookService.findByTenant(tenantId);
}
~~~

Context phải được thiết lập ở tầng request hoặc interceptor trước khi resolver đọc giá trị. Nếu key không tồn tại, hãy quyết định rõ cách xử lý giá trị null hoặc cung cấp default phù hợp.

Có thể truy cập DataFetchingEnvironment khi cần thông tin chi tiết hơn:

~~~java
@QueryMapping
public Book book(
        @Argument String id,
        DataFetchingEnvironment environment) {
    GraphQLContext context = environment.getGraphQlContext();
    return bookService.findById(id);
}
~~~

Không nên dùng DataFetchingEnvironment thay cho mọi tham số. Hãy ưu tiên @Argument và các kiểu tham số chuyên biệt để chữ ký resolver thể hiện rõ dữ liệu nó cần.

## Constructor injection và tổ chức service

Controller nên tập trung vào ánh xạ GraphQL field, còn nghiệp vụ nên nằm trong service. Constructor injection làm rõ dependency bắt buộc và hỗ trợ kiểm thử:

~~~java
@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public Book findById(String id) {
        return bookRepository.findById(id).orElse(null);
    }

    public List<Book> findAll() {
        return bookRepository.findAll();
    }
}
~~~

Trong ví dụ, service điều phối repository và có thể chứa validation, transaction hoặc quy tắc nghiệp vụ. Controller gọi service và trả kết quả cho GraphQL runtime. Tách lớp theo trách nhiệm giúp cùng một nghiệp vụ được sử dụng từ GraphQL, REST hoặc message consumer.

Không lưu dữ liệu request vào field mutable của controller. Spring bean thường có scope singleton, nên nhiều request có thể cùng gọi một instance controller. Dữ liệu theo request nên được truyền qua tham số, context hoặc một bean có scope phù hợp.

## Kiểu trả về của resolver

Annotated controller có thể trả về giá trị đồng bộ hoặc bất đồng bộ. Một số kiểu thường gặp:

| Kiểu trả về | Ý nghĩa |
| --- | --- |
| Object hoặc scalar Java | Kết quả đồng bộ |
| Collection hoặc List | Nhiều giá trị được trả về như danh sách |
| Mono<T> | Kết quả reactive có tối đa một giá trị |
| Flux<T> | Chuỗi reactive gồm nhiều giá trị |
| CompletionStage<T> | Kết quả bất đồng bộ theo Java CompletionStage |

Ví dụ resolver reactive:

~~~java
@Controller
public class ReactiveBookController {

    private final ReactiveBookService bookService;

    public ReactiveBookController(ReactiveBookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Mono<Book> book(@Argument String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public Flux<Book> books() {
        return bookService.findAll();
    }
}
~~~

GraphQL runtime phối hợp các kết quả bất đồng bộ trong quá trình thực thi. Dùng Mono hoặc Flux không tự làm cho thao tác blocking trở thành non-blocking; service và repository cần hỗ trợ reactive nếu muốn giữ mô hình non-blocking xuyên suốt.

## Batch mapping cho field quan hệ

Khi một query lấy nhiều object và mỗi object cần một field liên quan, resolver thông thường có thể gây N+1. **@BatchMapping** cho phép xử lý field đó theo nhóm:

~~~java
@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findAuthorsFor(books);
    }
}
~~~

Phương thức nhận danh sách source object và trả về kết quả tương ứng cho từng Book. Service cần thực hiện truy vấn theo lô thực sự để giảm số lần truy cập database hoặc dịch vụ ngoài. Chi tiết về DataLoader và batch loading nên được thiết kế cùng tầng service/repository.

## Bảo mật trên controller

Controller là một vị trí có thể áp dụng method security cho resolver. Ví dụ:

~~~java
@Controller
public class AdminGraphQlController {

    @PreAuthorize("hasRole('ADMIN')")
    @QueryMapping
    public List<AuditEntry> auditLog() {
        return auditService.findRecentEntries();
    }
}
~~~

Để annotation @PreAuthorize có hiệu lực, ứng dụng phải bật method security trong cấu hình Spring Security. Cần kiểm tra quyền truy cập theo người dùng, object và field; chỉ xác thực ở HTTP endpoint là chưa đủ với các query có nhiều field lồng nhau.

## Xử lý lỗi trong annotated controller

Resolver có thể phát sinh exception khi không tìm thấy dữ liệu, input không hợp lệ hoặc service ngoài gặp sự cố. Spring for GraphQL hỗ trợ xử lý lỗi qua cơ chế như DataFetcherExceptionResolver hoặc @GraphQlExceptionHandler trong annotated controller.

Ví dụ một handler có thể chuyển exception nghiệp vụ thành GraphQL error có thông điệp phù hợp:

~~~java
@Controller
public class GraphQlErrorHandler {

    @GraphQlExceptionHandler
    public GraphQLError handle(BookNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .message("Không tìm thấy sách")
                .errorType(ErrorType.NOT_FOUND)
                .build();
    }
}
~~~

Tên và chữ ký API cụ thể cần khớp với phiên bản Spring for GraphQL trong dự án. Thông báo gửi client không nên chứa stack trace, câu SQL, token hoặc thông tin nội bộ. Với validation, hãy trả lỗi đủ rõ để client biết field hoặc input nào không hợp lệ.

## Kiểm thử annotated controller

Spring for GraphQL cung cấp GraphQlTester để kiểm thử operation mà không phải tự tạo và phân tích JSON response. Ví dụ:

~~~java
graphQlTester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-101")
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Spring in Action");
~~~

Nên kiểm tra cả mapping đúng, argument thiếu hoặc sai, dữ liệu không tồn tại, quyền truy cập, exception và field lồng nhau. Nếu cần kiểm tra toàn bộ HTTP transport, có thể dùng HttpGraphQlTester kết hợp WebTestClient hoặc tester phù hợp với web stack của ứng dụng.

## Lỗi thường gặp khi dùng @Controller

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Resolver không được gọi | Controller không được component scan hoặc thiếu annotation mapping | Kiểm tra package và bean registration |
| Field không có data fetcher phù hợp | Tên field hoặc typeName không khớp SDL | Kiểm tra @QueryMapping, @SchemaMapping và schema |
| Argument nhận null | Tên @Argument sai hoặc client không truyền biến | So sánh tên argument trong SDL và operation |
| Input object không bind được | Kiểu Java không tương thích cấu trúc SDL | Kiểm tra DTO, constructor và kiểu field |
| Field lồng nhau trả null | Property accessor hoặc resolver con không cung cấp giá trị | Kiểm tra source object và @SchemaMapping |
| Request bị chặn ở event loop | Resolver reactive gọi thư viện blocking | Kiểm tra service/repository và cách dùng scheduler |
| Method security không hoạt động | Chưa bật method security hoặc method không đi qua proxy | Kiểm tra cấu hình Spring Security |

## Nguyên tắc tổ chức annotated controller

Khi xây dựng GraphQL controller, nên giữ một số nguyên tắc:

1. **Dùng @Controller cho annotated GraphQL handler.** Đặt lớp trong package được Spring component scan.
2. **Ánh xạ rõ ràng theo schema.** Tên method, field, typeName và argument phải khớp SDL.
3. **Giữ controller mỏng.** Controller nhận input, gọi service và trả kết quả; nghiệp vụ nằm trong service.
4. **Dùng constructor injection.** Khai báo dependency bắt buộc rõ ràng và dễ kiểm thử.
5. **Chọn kiểu trả về phù hợp.** Dùng reactive publisher khi các tầng bên dưới hỗ trợ non-blocking.
6. **Bảo vệ field theo quyền truy cập.** Kết hợp Spring Security với kiểm tra quyền ở service hoặc data access.
7. **Kiểm thử operation thực tế.** Bao phủ query, mutation, subscription, field mapping và lỗi theo yêu cầu của API.

Trong Spring for GraphQL, @Controller là điểm tổ chức các resolver theo mô hình bean của Spring. Các annotation mapping liên kết phương thức Java với field trong SDL; argument và source object cung cấp dữ liệu cho phương thức; service đảm nhiệm nghiệp vụ; GraphQL runtime điều phối việc thực thi và tạo response. Khi giữ ranh giới này rõ ràng, controller dễ đọc, dễ kiểm thử và có thể mở rộng khi schema phát triển.
