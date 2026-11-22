# Method return value

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích cách giá trị trả về của method resolver trở thành giá trị của GraphQL field.
- Chọn kiểu Java phù hợp khi resolver trả scalar, object hoặc danh sách.
- Hiểu tác động của null, collection rỗng và nullability trong SDL.
- Trả kết quả bất đồng bộ bằng CompletionStage, Mono hoặc Flux.
- Phân biệt Flux dùng cho field collection với stream của subscription.
- Dùng DataFetcherResult khi cần trả dữ liệu kèm GraphQL errors hoặc local context.
- Kiểm thử kết quả resolver bằng GraphQlTester.

## Giá trị method trở thành giá trị field như thế nào?

Trong Spring for GraphQL, annotated controller method đóng vai trò resolver cho một GraphQL field. Giá trị method trả về được GraphQL runtime dùng làm kết quả của field đó. Spring hỗ trợ nhiều kiểu trả về để controller có thể làm việc với dữ liệu đồng bộ, bất đồng bộ hoặc reactive.

Ví dụ schema:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Resolver:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }
}
~~~

Method trả về một object Book. GraphQL không serialize toàn bộ object Java thành một khối JSON theo cách tùy ý. Thay vào đó, runtime tiếp tục phân giải những field mà client đã chọn, chẳng hạn Book.id và Book.title. Các field đó có thể lấy từ property/getter mặc định hoặc resolver @SchemaMapping riêng.

Điều này có nghĩa selection set của client quyết định những field nào được thực thi. Resolver bookById cung cấp object nguồn; các resolver cấp dưới cung cấp dữ liệu cho những field con cần thiết.

## Chọn kiểu trả về theo GraphQL type

Kiểu Java nên thể hiện đúng loại dữ liệu mà schema công bố:

| GraphQL field | Kiểu Java thường dùng | Ví dụ |
| --- | --- | --- |
| Scalar | String, Integer, Boolean, BigDecimal, kiểu tương ứng với custom scalar | String title() |
| Object | Domain object hoặc DTO | Book bookById(...) |
| List | List<T>, Collection<T> hoặc mảng phù hợp | List<Book> books() |
| Giá trị có thể vắng mặt | Kiểu tham chiếu và trả null khi không có giá trị | Book findBook(...) |
| Kết quả bất đồng bộ | CompletionStage<T>, Mono<T> | Mono<Book> bookById(...) |
| Luồng sự kiện subscription | Flux<T> hoặc Publisher<T> | Flux<Book> bookAdded() |

Kiểu Java không cần trùng tên với GraphQL type. Điều quan trọng là GraphQL runtime có thể đọc các field con và xác định đúng concrete type khi schema dùng interface hoặc union.

### Trả về scalar

Với field scalar, method trả về giá trị tương ứng:

~~~graphql
type Query {
  serviceName: String!
  bookCount: Int!
}
~~~

~~~java
@QueryMapping
public String serviceName() {
    return "library-api";
}

@QueryMapping
public int bookCount() {
    return bookService.count();
}
~~~

GraphQL serialize giá trị theo scalar đã khai báo. Với custom scalar, giá trị Java phải tương thích với implementation đã đăng ký trong runtime wiring. Ví dụ một scalar DateTime có thể yêu cầu OffsetDateTime; không nên giả định mọi kiểu ngày giờ Java đều được chuyển đổi tự động.

### Trả về object

Method có thể trả domain object hoặc DTO:

~~~java
@QueryMapping
public Book bookById(@Argument("id") String id) {
    return bookService.findById(id).orElse(null);
}
~~~

Nếu client chỉ chọn id và title, GraphQL chỉ cần phân giải hai field đó. Nếu client chọn thêm author, runtime tiếp tục xử lý Book.author. Field này có thể lấy từ property của Book hoặc từ method @SchemaMapping.

Nên trả DTO hoặc domain model phù hợp với GraphQL schema. Tránh trả entity persistence có quan hệ lazy không được kiểm soát nếu việc đọc field có thể kích hoạt truy vấn ngoài dự kiến.

### Trả về collection

Với field list, có thể trả List<T>:

~~~graphql
type Query {
  booksByAuthor(authorId: ID!): [Book!]!
}
~~~

~~~java
@QueryMapping
public List<Book> booksByAuthor(
        @Argument("authorId") String authorId) {
    return bookService.findByAuthorId(authorId);
}
~~~

Thứ tự phần tử trong response theo thứ tự collection mà resolver trả về. Nếu API cần thứ tự ổn định, hãy sắp xếp ở service hoặc truy vấn dữ liệu có ORDER BY rõ ràng; không dựa vào thứ tự ngẫu nhiên của database.

Một collection rỗng thường được biểu diễn bằng list rỗng [], khác với null. Nên trả collection rỗng khi truy vấn thành công nhưng không có phần tử. Trả null chỉ khi semantics của field cho phép biểu thị không có giá trị.

## Nullability quyết định cách xử lý giá trị thiếu

GraphQL SDL xác định field có thể trả null hay không:

~~~graphql
type Query {
  optionalBook(id: ID!): Book
  requiredBooks: [Book!]!
}

type Book {
  id: ID!
  title: String!
}
~~~

optionalBook có thể trả null nếu không tìm thấy sách. requiredBooks phải trả về một list khác null, và mọi phần tử trong list cũng phải khác null.

Các trường hợp thường gặp:

| SDL | Giá trị được phép |
| --- | --- |
| Book | Object hoặc null |
| Book! | Object khác null |
| [Book] | List hoặc null; phần tử có thể null |
| [Book!] | List hoặc null; phần tử không được null |
| [Book]! | List khác null; phần tử có thể null |
| [Book!]! | List khác null; mọi phần tử khác null |

Nếu resolver trả null cho field non-null, GraphQL tạo execution error và lan truyền null lên field cha gần nhất có thể nhận null. Nếu field cha cũng non-null, lỗi tiếp tục lan lên cao hơn. Vì vậy, chọn ! chỉ khi server thực sự bảo đảm giá trị luôn có mặt trong mọi trường hợp hợp lệ.

Ví dụ, nếu Book.title là String!, resolver của title không được trả null. Nếu nguồn dữ liệu cũ có sách thiếu title, cần xử lý dữ liệu hoặc xác định quy tắc nghiệp vụ phù hợp trước khi công bố field non-null.

### Không tìm thấy object

Nếu field được khai báo nullable, có thể trả null khi không tìm thấy:

~~~java
@QueryMapping
public Book bookById(@Argument("id") String id) {
    return bookService.findById(id).orElse(null);
}
~~~

Nếu muốn trả lỗi có ý nghĩa như BOOK_NOT_FOUND, có thể ném exception nghiệp vụ và ánh xạ sang GraphQL error bằng DataFetcherExceptionResolver. Không nên đổi field thành non-null chỉ để buộc GraphQL báo lỗi khi object không tồn tại; nullability mô tả contract dữ liệu, còn lỗi nghiệp vụ cần được biểu diễn theo chính sách API.

Nếu service trả Optional<Book>, hãy quyết định rõ semantics và chuyển thành giá trị phù hợp trước khi trả về resolver, ví dụ orElse(null) hoặc ném exception. Không dựa vào việc Optional tự động được serialize như một GraphQL object.

## Giá trị trả về của field lồng nhau

Method @SchemaMapping nhận source object và trả giá trị cho field trên object đó:

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

~~~java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId()).orElse(null);
    }
}
~~~

Ở đây, Book là source object; method trả về Author làm giá trị của Book.author. GraphQL tiếp tục phân giải Author.id và Author.name theo selection set.

Nếu Book đã có property author chứa sẵn object Author, có thể không cần viết resolver riêng. Khi dữ liệu cần truy vấn thêm, @SchemaMapping giúp kiểm soát cách lấy giá trị.

## Trả về bất đồng bộ bằng CompletionStage

Nếu service đã có API bất đồng bộ dựa trên Java CompletionStage, resolver có thể trả trực tiếp kiểu đó:

~~~java
@QueryMapping
public CompletionStage<Book> bookById(@Argument("id") String id) {
    return bookService.findByIdAsync(id);
}
~~~

CompletableFuture<T> là một implementation phổ biến của CompletionStage<T>. GraphQL runtime chờ kết quả hoàn tất trước khi hoàn thiện field tương ứng. Các field độc lập có thể được thực thi bất đồng bộ theo cơ chế của GraphQL Java.

Không nên gọi .join() hoặc .get() ngay trong controller để chờ future hoàn tất. Làm vậy sẽ biến thao tác bất đồng bộ thành blocking và giữ thread trong lúc chờ.

Nếu cần chạy tác vụ blocking trên executor riêng, hãy thiết kế service có chủ đích và dùng executor được quản lý phù hợp. Không tùy tiện dùng common pool cho các lời gọi I/O có thời gian chờ dài.

## Trả về Mono và Flux trong ứng dụng reactive

Spring for GraphQL hỗ trợ các kiểu reactive như Mono<T> và Flux<T>. Chúng hữu ích khi service sử dụng reactive repository hoặc reactive HTTP client.

### Mono cho một giá trị

Mono<T> biểu diễn tối đa một giá trị:

~~~java
@QueryMapping
public Mono<Book> bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

Một Mono có thể phát ra một object hoặc hoàn tất mà không có giá trị. Trường hợp không có giá trị được xử lý như kết quả null, vì vậy cần đối chiếu với nullability của field trong SDL.

### Flux cho danh sách ở query thông thường

Flux<T> biểu diễn một chuỗi phần tử. Với field query thông thường, Spring for GraphQL thu thập các phần tử thành kết quả collection để GraphQL xử lý như một list:

~~~java
@QueryMapping
public Flux<Book> books() {
    return bookService.findAll();
}
~~~

Nếu không có phần tử, kết quả collection là list rỗng. Với danh sách lớn, cần phân trang hoặc giới hạn kích thước; không nên phát một lượng dữ liệu không giới hạn rồi thu thập toàn bộ vào bộ nhớ.

Có thể dùng Mono<List<Book>> nếu service trả về một list bất đồng bộ. Chọn kiểu trả về phù hợp với API của service và cách tải dữ liệu; không cần chuyển mọi collection thành Flux nếu không có lợi ích thực tế.

### Không block reactive pipeline

Không gọi .block() trong resolver để lấy giá trị từ Mono hoặc Flux:

~~~java
// Không nên: chặn thread để đợi reactive result.
@QueryMapping
public Book bookById(@Argument("id") String id) {
    return bookService.findById(id).block();
}
~~~

Hãy trả reactive type trực tiếp:

~~~java
@QueryMapping
public Mono<Book> bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

Việc trả Mono hoặc Flux không tự biến lời gọi blocking bên trong thành non-blocking. Nếu service dùng JDBC hoặc HTTP client blocking, pipeline vẫn có thể chặn thread. Muốn tận dụng WebFlux, hãy dùng reactive data access/client hoặc cô lập thao tác blocking trên scheduler/executor phù hợp.

## Flux trong Subscription khác Flux trong Query

Với query collection, Flux<T> được thu thập thành list để tạo một response GraphQL thông thường. Với subscription, Flux<T> là luồng sự kiện được phát dần qua transport hỗ trợ streaming.

Schema:

~~~graphql
type Subscription {
  bookAdded: Book!
}
~~~

Resolver:

~~~java
@Controller
public class BookSubscriptionController {

    private final BookEventService eventService;

    public BookSubscriptionController(BookEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<Book> bookAdded() {
        return eventService.bookAdded();
    }
}
~~~

Mỗi phần tử do Flux phát ra trở thành một kết quả subscription. Client nhận các sự kiện theo thời gian qua transport như WebSocket hoặc Server-Sent Events tùy cấu hình. Khi client hủy subscription hoặc ngắt kết nối, nguồn sự kiện nên giải phóng đăng ký và tài nguyên liên quan.

Không dùng Flux cho subscription chỉ vì field trả về list. Query và subscription có semantics khác nhau: query tạo một response cho một lần thực thi, còn subscription duy trì một luồng kết quả.

## Trả về DataFetcherResult khi cần dữ liệu kèm metadata hoặc lỗi

Thông thường resolver chỉ cần trả giá trị field. Trong trường hợp cần gắn GraphQL errors hoặc local context cùng dữ liệu, GraphQL Java cung cấp DataFetcherResult<T>.

Ví dụ:

~~~java
import graphql.GraphqlErrorBuilder;
import graphql.execution.DataFetcherResult;

@QueryMapping
public DataFetcherResult<Book> bookDetails(
        @Argument("id") String id) {

    Book book = bookService.findById(id).orElse(null);
    if (book == null) {
        return DataFetcherResult.<Book>newResult()
                .data(null)
                .error(GraphqlErrorBuilder.newError()
                        .message("Không tìm thấy sách")
                        .build())
                .build();
    }

    return DataFetcherResult.<Book>newResult()
            .data(book)
            .build();
}
~~~

DataFetcherResult cho phép trả data cùng một hoặc nhiều GraphQLError. Nó hữu ích khi cần biểu diễn lỗi ở cấp field và vẫn giữ được phần dữ liệu hợp lệ theo semantics của GraphQL. Tuy nhiên, nếu field được khai báo non-null, việc trả data(null) vẫn có thể kích hoạt null propagation.

Không dùng DataFetcherResult chỉ để thay thế kiểu trả về thông thường. Với lỗi phát sinh trong service, có thể dùng exception resolver chung để chuẩn hóa lỗi; với kết quả có data và errors cùng lúc, DataFetcherResult là lựa chọn phù hợp hơn.

DataFetcherResult còn hỗ trợ local context và extensions. Local context có thể được truyền tới các resolver field con khi cần chia sẻ dữ liệu nội bộ trong quá trình phân giải một nhánh. Chỉ đưa dữ liệu cần thiết vào context và không dùng nó làm nơi lưu trạng thái toàn cục giữa các request.

## Kết hợp giá trị trả về với type resolution

Nếu schema trả về interface hoặc union, GraphQL runtime phải xác định object type cụ thể của giá trị Java. Ví dụ:

~~~graphql
interface SearchResult {
  id: ID!
  title: String!
}

type Book implements SearchResult {
  id: ID!
  title: String!
  isbn: String!
}

type Article implements SearchResult {
  id: ID!
  title: String!
  url: String!
}

type Query {
  search: [SearchResult!]!
}
~~~

Resolver có thể trả về List<SearchResult> chứa các object Book và Article:

~~~java
@QueryMapping
public List<SearchResult> search() {
    return searchService.search();
}
~~~

GraphQL cần xác định mỗi object Java tương ứng với Book hay Article. Nếu cơ chế type resolution mặc định không suy ra đúng kiểu, hãy đăng ký TypeResolver qua RuntimeWiringConfigurer. Giá trị trả về đúng Java interface nhưng thiếu type resolution phù hợp vẫn có thể gây lỗi khi GraphQL thực thi.

Khi thêm một concrete type mới, kiểm tra cả giá trị resolver trả về lẫn mapping type runtime. Không nên chỉ kiểm thử rằng danh sách Java có phần tử; hãy xác minh __typename trong GraphQL response.

## Hiệu năng và phạm vi công việc của resolver

Kiểu trả về không quyết định toàn bộ hiệu năng. Một method trả Mono<Book> vẫn có thể gọi database blocking; một method trả List<Book> có thể tải quá nhiều dữ liệu; một resolver field con có thể gây N+1.

Khi thiết kế resolver:

- Dùng phân trang cho collection lớn và giới hạn page size.
- Chỉ truy vấn dữ liệu cần cho field được yêu cầu khi có thể.
- Dùng @BatchMapping hoặc DataLoader để gom truy vấn cho các field quan hệ được gọi nhiều lần.
- Tránh trả entity có lazy relationship nếu việc truy cập property gây truy vấn ngoài dự kiến.
- Không block trên reactive pipeline.
- Đo thời gian và số lần gọi repository/service khi kiểm thử query có nhiều field lồng nhau.

Ví dụ, query lấy 50 sách và mỗi sách có field author có thể tạo 50 lượt gọi AuthorService nếu resolver tải từng tác giả riêng. Chuyển sang @BatchMapping hoặc DataLoader có thể gom việc tải tác giả thành một lần theo batch.

## Kiểm thử method return value bằng GraphQlTester

GraphQlTester kiểm tra kết quả sau khi GraphQL runtime thực thi resolver, bất kể method trả object đồng bộ hay kiểu bất đồng bộ.

Ví dụ query object:

~~~java
graphQlTester.document("""
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-101")
    .execute()
    .path("bookById.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL Guide");
~~~

Nên kiểm thử các trường hợp:

1. Scalar trả về đúng kiểu và giá trị.
2. Object trả về phân giải được các field con.
3. List giữ đúng thứ tự, list rỗng trả [].
4. Field nullable trả null khi không có dữ liệu.
5. Field non-null không trả null trong các trường hợp hợp lệ.
6. Mono hoặc CompletionStage hoàn tất với giá trị mong đợi.
7. Mono.empty() được xử lý đúng theo nullability.
8. Resolver lỗi tạo GraphQL error đúng contract.
9. DataFetcherResult trả data và errors như dự kiến.
10. Subscription phát sự kiện và dừng khi client hủy đăng ký.

Với subscription, cần dùng tester hoặc integration test phù hợp với transport streaming đã cấu hình. Một test query thông thường không xác minh được handshake WebSocket/SSE, vòng đời stream và cancellation.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Field object trả về nhưng field con null | Object thiếu property/getter hoặc thiếu @SchemaMapping | Kiểm tra source object và resolver field con |
| GraphQL báo lỗi non-null | Resolver trả null cho field có dấu ! | Sửa dữ liệu/logic hoặc điều chỉnh nullability theo contract |
| List trả null thay vì [] | Service trả null cho collection | Chuẩn hóa kết quả không có phần tử thành list rỗng |
| Query reactive vẫn block | Có lời gọi blocking hoặc gọi .block() trong resolver | Trả reactive type trực tiếp hoặc cô lập tác vụ blocking |
| Subscription chỉ trả một response | Dùng query mapping hoặc transport không hỗ trợ stream | Dùng @SubscriptionMapping và cấu hình transport |
| Interface/union không phân giải được | Runtime không xác định được concrete GraphQL type | Cấu hình TypeResolver và kiểm thử __typename |
| Response có lỗi dù có data | DataFetcherResult chứa errors hoặc field con phát sinh lỗi | Kiểm tra errors và nullability của nhánh response |
| Query danh sách chậm | Resolver field con tạo N+1 hoặc tải quá nhiều dữ liệu | Phân trang và dùng batching/DataLoader |

## Thực hành tổng hợp

Xây dựng API thư viện với các resolver sau:

1. bookById(id: ID!): Book trả Book hoặc null khi không tìm thấy.
2. books(first: Int!): [Book!]! trả list có giới hạn và list rỗng khi không có sách.
3. Book.author: Author dùng @SchemaMapping để lấy tác giả.
4. Chuyển bookById sang trả Mono<Book> nếu service dùng reactive repository.
5. Tạo một method bất đồng bộ trả CompletionStage<Book> nếu service đã cung cấp API đó.
6. Thêm @SubscriptionMapping trả Flux<Book> cho sự kiện sách mới.
7. Dùng DataFetcherResult<Book> cho một use case cần trả field error có cấu trúc.
8. Viết GraphQlTester kiểm tra object, list, null, lỗi và các field lồng nhau.

Sau khi hoàn thành, hãy giải thích vì sao Mono<Book> phù hợp cho một giá trị, Flux<Book> có semantics khác nhau giữa query và subscription, và vì sao field non-null không được trả null.

## Ghi nhớ

Giá trị method resolver trở thành giá trị của GraphQL field. Scalar được serialize theo scalar type; object được dùng làm source để phân giải các field con; collection trở thành list. Nullability trong SDL quyết định field có được phép thiếu giá trị và cách GraphQL lan truyền lỗi. Spring for GraphQL hỗ trợ kiểu đồng bộ, CompletionStage, Mono, Flux và DataFetcherResult; hãy chọn theo semantics của field và service. Query collection thu thập phần tử thành list, còn subscription dùng publisher để phát sự kiện theo thời gian. Không block reactive pipeline, kiểm soát N+1 và kiểm thử kết quả cùng lỗi bằng GraphQlTester.
