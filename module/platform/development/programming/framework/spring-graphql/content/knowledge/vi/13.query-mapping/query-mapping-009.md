# Query reactive

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích cách Spring for GraphQL hỗ trợ các kiểu trả về reactive trong Query.
- Phân biệt Mono và Flux khi mapping vào GraphQL field đơn hoặc danh sách.
- Viết Query controller kết hợp các reactive service mà không chặn thread.
- Kết hợp nhiều nguồn dữ liệu bằng các toán tử Reactor.
- Hiểu vì sao Flux trong Query không đồng nghĩa với Subscription streaming.
- Xử lý Mono rỗng, lỗi reactive và nullability của schema.
- Giới hạn dữ liệu, tránh fan-out không kiểm soát và kiểm thử Query reactive bằng GraphQlTester.

## 1. Query reactive là gì?

Trong GraphQL, Query là operation dùng để đọc dữ liệu. Với Spring for GraphQL, method được đánh dấu bằng @QueryMapping có thể trả về object đồng bộ hoặc kiểu reactive như Mono và Flux.

Reactive programming biểu diễn kết quả như một luồng dữ liệu bất đồng bộ. Thay vì buộc một thread chờ database hoặc service khác trả lời, controller trả về publisher để framework phối hợp quá trình thực thi.

Hai kiểu Reactor thường gặp:

| Kiểu | Số kết quả | Trường hợp dùng |
|---|---:|---|
| Mono<T> | 0 hoặc 1 | Lấy một quyển sách, hồ sơ hoặc tổng số |
| Flux<T> | 0 đến nhiều | Lấy danh sách sách, kết quả tìm kiếm hoặc các phần tử của một field list |

Ví dụ:

~~~java
@QueryMapping
public Mono<Book> book(@Argument String id) {
    return bookService.findById(id);
}

@QueryMapping
public Flux<Book> books() {
    return bookService.findAll();
}
~~~

Spring for GraphQL tích hợp reactive return types thông qua cơ chế reactive adapter. Khi field GraphQL là một object đơn, Mono biểu diễn kết quả bất đồng bộ của field đó. Với field danh sách, Flux có thể cung cấp các phần tử cho kết quả list.

Điều này cho phép controller giữ nguyên mô hình reactive của service hoặc repository. Bạn không cần tự gọi subscribe để lấy kết quả trước khi trả về.

## 2. Khai báo schema cho Query reactive

Kiểu trả về Java phải phù hợp với kiểu GraphQL được khai báo trong SDL. Reactive không làm thay đổi schema; nó chỉ thay đổi cách server tạo ra giá trị cho field.

Ví dụ schema:

~~~graphql
type Query {
  book(id: ID!): Book
  books(first: Int = 20): [Book!]!
  searchBooks(keyword: String!, first: Int = 20): [Book!]!
}

type Book {
  id: ID!
  title: String!
  publishedYear: Int
}
~~~

Các mapping có thể dùng Mono hoặc Flux:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Mono<Book> book(@Argument String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public Flux<Book> books(@Argument Integer first) {
        int limit = first == null ? 20 : first;
        return bookService.findFirst(limit);
    }

    @QueryMapping
    public Flux<Book> searchBooks(
            @Argument String keyword,
            @Argument Integer first) {
        int limit = first == null ? 20 : first;
        return bookService.search(keyword, limit);
    }
}
~~~

Ví dụ trên giả định BookService trả về các publisher tương ứng. Nếu service dùng kiểu đồng bộ, controller có thể trả về Book hoặc List<Book>; không cần chuyển mọi method sang reactive chỉ vì ứng dụng có dùng Spring GraphQL.

Nên giữ schema mô tả đúng nghiệp vụ. Ví dụ, book có thể trả null khi không tìm thấy nếu field được khai báo nullable; books nên trả về danh sách rỗng nếu không có kết quả và schema yêu cầu list non-null.

## 3. Mono cho một kết quả

Mono phù hợp khi một field chỉ trả về tối đa một giá trị, chẳng hạn truy vấn theo ID.

~~~java
@QueryMapping
public Mono<Book> book(@Argument String id) {
    return bookService.findById(id);
}
~~~

Service có thể dùng reactive repository:

~~~java
@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Mono<Book> findById(String id) {
        return repository.findById(id);
    }
}
~~~

Nếu không tìm thấy dữ liệu, reactive repository thường trả Mono.empty(). Khi publisher hoàn tất mà không có giá trị, field được xem là không có kết quả. Điều này tương ứng với null đối với một GraphQL field nullable.

Nếu schema khai báo field là non-null, ví dụ book(id: ID!): Book!, nhưng resolver không tìm thấy Book và hoàn tất rỗng, GraphQL phải tạo lỗi thực thi và áp dụng quy tắc null propagation.

Vì vậy, hãy chọn nullability dựa trên hợp đồng nghiệp vụ. Nếu không tìm thấy là tình huống bình thường, field có thể nullable. Nếu kết quả bắt buộc phải tồn tại, server cần xử lý trường hợp thiếu dữ liệu như một lỗi có chủ đích.

Có thể chuyển đổi kết quả rỗng thành lỗi nghiệp vụ:

~~~java
public Mono<Book> requireBook(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new BookNotFoundException(id)));
}
~~~

Không nên biến mọi trường hợp không tìm thấy thành lỗi nếu API được thiết kế để trả null. Hãy thống nhất hành vi giữa schema, service và client.

## 4. Flux cho field danh sách

Flux phù hợp khi service phát ra nhiều phần tử. Với GraphQL field có kiểu list, Spring for GraphQL chuyển kết quả reactive thành giá trị của field theo quá trình thực thi GraphQL.

~~~java
@QueryMapping
public Flux<Book> books(@Argument Integer first) {
    int limit = first == null ? 20 : first;
    return bookService.findFirst(limit);
}
~~~

SDL tương ứng:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}
~~~

Nếu không có quyển sách nào, Flux.empty() biểu diễn danh sách không có phần tử. Với field [Book!]!, kết quả danh sách rỗng vẫn hợp lệ vì danh sách tồn tại và không chứa phần tử null.

Có thể dùng Mono<List<Book>> nếu service đã tạo sẵn toàn bộ danh sách:

~~~java
@QueryMapping
public Mono<List<Book>> books() {
    return bookService.findAllAsList();
}
~~~

Hai cách này phục vụ những thiết kế service khác nhau. Flux phù hợp khi nguồn dữ liệu phát ra từng phần tử; Mono<List<Book>> phù hợp khi service trả về một danh sách đã được gom thành một giá trị. Hãy kiểm tra kiểu trả về mà service thực sự cung cấp và chọn cách biểu diễn rõ ràng.

Lưu ý: Query vẫn là request-response. Dù resolver trả về Flux, client nhận một GraphQL response theo operation với field list đã được giải quyết. Flux ở đây không tự biến Query thành một kết nối gửi từng phần tử thành nhiều response độc lập. Nếu cần nhận cập nhật liên tục theo thời gian, hãy dùng Subscription.

## 5. Kết hợp nhiều reactive service

Một Query có thể cần dữ liệu từ nhiều nguồn độc lập. Reactor cung cấp các toán tử để kết hợp publisher mà không cần block thread.

Ví dụ trang tổng quan sách cần thông tin Book và số lượng Review:

~~~graphql
type Query {
  bookSummary(id: ID!): BookSummary
}

type BookSummary {
  book: Book!
  reviewCount: Int!
}
~~~

DTO:

~~~java
public record BookSummary(Book book, Integer reviewCount) {
}
~~~

Controller:

~~~java
@QueryMapping
public Mono<BookSummary> bookSummary(@Argument String id) {
    Mono<Book> bookMono = bookService.findById(id);
    Mono<Integer> countMono = reviewService.countByBookId(id);

    return Mono.zip(bookMono, countMono)
            .map(tuple -> new BookSummary(
                    tuple.getT1(),
                    tuple.getT2()));
}
~~~

Mono.zip đăng ký các publisher đầu vào và kết hợp kết quả khi chúng có giá trị. Hai tác vụ độc lập có thể tiến triển bất đồng bộ mà không cần viết callback lồng nhau.

Nếu một publisher hoàn tất rỗng, Mono.zip không tạo tuple. Vì vậy, hãy quyết định rõ trường hợp Book không tồn tại: có thể kiểm tra Book trước bằng flatMap, hoặc chuyển kết quả rỗng thành lỗi nếu nghiệp vụ yêu cầu.

~~~java
@QueryMapping
public Mono<BookSummary> bookSummary(@Argument String id) {
    return bookService.findById(id)
            .switchIfEmpty(Mono.error(
                    new BookNotFoundException(id)))
            .flatMap(book ->
                    reviewService.countByBookId(id)
                            .map(count ->
                                    new BookSummary(book, count)));
}
~~~

Ví dụ thứ hai bảo đảm chỉ truy vấn số review sau khi đã tìm thấy Book. Cách dùng flatMap phù hợp khi bước sau phụ thuộc kết quả của bước trước.

Một số toán tử thường dùng:

| Toán tử | Mục đích |
|---|---|
| map | Chuyển đổi giá trị đồng bộ |
| flatMap | Chuyển một giá trị thành publisher khác |
| zip | Kết hợp kết quả từ nhiều publisher |
| filter | Giữ lại giá trị thỏa điều kiện |
| switchIfEmpty | Chọn publisher thay thế khi không có giá trị |
| onErrorMap | Chuyển loại lỗi |
| onErrorResume | Chọn publisher thay thế khi có lỗi |

## 6. Phân biệt map và flatMap

Dùng map khi phép biến đổi trả về một giá trị thông thường. Dùng flatMap khi phép biến đổi tiếp tục trả về Mono hoặc Flux.

~~~java
Mono<String> title = bookService.findById("b-01")
        .map(Book::getTitle);
~~~

Ở đây, Book được chuyển thành String.

~~~java
Mono<Author> author = bookService.findById("b-01")
        .flatMap(book ->
                authorService.findById(book.getAuthorId()));
~~~

Ở đây, thao tác lấy Author cũng bất đồng bộ và trả về Mono<Author>, vì vậy cần flatMap để làm phẳng publisher.

Nếu dùng map trong trường hợp thứ hai, kết quả sẽ là Mono<Mono<Author>>, khiến kiểu dữ liệu lồng nhau không phù hợp với mục tiêu.

## 7. Tránh block() và subscribe() trong controller

Một lỗi phổ biến khi chuyển code đồng bộ sang reactive là gọi block() để lấy giá trị ngay:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id).block();
}
~~~

Cách này làm thread phải chờ publisher hoàn tất. Nó phá vỡ lợi ích của mô hình reactive và có thể gây nghẽn khi tải cao hoặc khi chạy trên event-loop thread.

Một lỗi khác là tự subscribe trong controller:

~~~java
@QueryMapping
public Mono<Book> book(@Argument String id) {
    bookService.findById(id).subscribe();
    return Mono.empty();
}
~~~

subscribe() tự khởi chạy một luồng xử lý tách rời khỏi GraphQL request. Framework không còn kiểm soát đầy đủ kết quả, lỗi và thời điểm hoàn tất của thao tác đó.

Hãy trả publisher trực tiếp:

~~~java
@QueryMapping
public Mono<Book> book(@Argument String id) {
    return bookService.findById(id);
}
~~~

Spring for GraphQL quản lý việc subscribe và tích hợp kết quả vào quá trình thực thi GraphQL. Controller chỉ nên mô tả pipeline cần chạy.

Không gọi block(), subscribe() hoặc tạo side effect tách rời trong resolver thông thường. Với thao tác nền không thuộc vòng đời GraphQL request, hãy đưa nó vào thành phần xử lý riêng có cơ chế quản lý vòng đời rõ ràng.

## 8. Kết hợp hệ thống blocking với reactive code

Không phải thư viện nào trong ứng dụng cũng hỗ trợ reactive. Ví dụ, một repository JPA đồng bộ có thể cần được gọi trong lúc chuyển đổi dần hệ thống.

Nếu bắt buộc phải gọi một API blocking, có thể cô lập thao tác đó bằng Mono.fromCallable và đưa sang boundedElastic:

~~~java
public Mono<Book> findById(String id) {
    return Mono.fromCallable(() ->
                    jpaRepository.findById(id).orElse(null))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Cách này giúp thao tác blocking không chạy trực tiếp trên event-loop thread. Tuy nhiên, nó không biến JPA thành reactive repository; thread vẫn bị chiếm trong lúc lời gọi database chạy.

Không dùng Schedulers.parallel() cho tác vụ blocking. Không bọc mọi lời gọi một cách máy móc nếu đã có reactive driver hoặc reactive client tương ứng. Với hệ thống tải cao, nên ưu tiên nguồn dữ liệu non-blocking như R2DBC hoặc reactive HTTP client khi kiến trúc phù hợp.

Nếu một resolver gọi nhiều dịch vụ blocking, việc chuyển từng lời gọi sang boundedElastic vẫn tiêu thụ thread. Cần đo lường và giới hạn tải thay vì xem boundedElastic là tài nguyên vô hạn.

## 9. Xử lý lỗi trong reactive Query

Lỗi có thể phát sinh khi truy vấn database, gọi service bên ngoài hoặc chuyển đổi dữ liệu. Reactor truyền lỗi dọc theo publisher cho đến khi có toán tử xử lý hoặc GraphQL nhận lỗi.

Ví dụ chuyển lỗi kỹ thuật thành lỗi nghiệp vụ:

~~~java
public Mono<Book> findById(String id) {
    return repository.findById(id)
            .onErrorMap(
                    DataAccessException.class,
                    ex -> new BookLookupException(
                            "Cannot load book " + id, ex)
            );
}
~~~

Với Spring for GraphQL, có thể dùng DataFetcherExceptionResolver để chuyển exception thành GraphQL error có thông tin phù hợp cho client. Không nên đưa SQL, stack trace hoặc thông tin nhạy cảm vào thông báo lỗi công khai.

Chỉ dùng onErrorResume khi thực sự có giá trị thay thế hợp lệ:

~~~java
public Mono<Book> findFeaturedBook() {
    return bookService.findFeatured()
            .onErrorResume(
                    FeaturedBookUnavailableException.class,
                    ex -> bookService.findFallback()
            );
}
~~~

Không nên dùng onErrorResume(error -> Mono.empty()) cho mọi lỗi. Cách đó có thể che giấu sự cố database hoặc service và khiến client hiểu nhầm rằng dữ liệu đơn giản là không tồn tại.

### Lỗi và nullability

GraphQL xử lý kết quả lỗi theo schema:

- Field nullable có thể nhận null kèm errors trong response.
- Field non-null không được phép trả null; lỗi có thể lan lên parent field gần nhất cho phép null.
- Nếu nhiều field độc lập được thực thi, lỗi của một field không nhất thiết làm mất dữ liệu của tất cả field khác.

Hãy thiết kế nullability theo ý nghĩa nghiệp vụ và kiểm thử cả trường hợp publisher rỗng lẫn publisher phát lỗi.

## 10. Giới hạn truy vấn và pagination

Reactive không đồng nghĩa với dữ liệu có thể tải vô hạn. Một Flux có thể phát ra rất nhiều phần tử, nhưng GraphQL Query thường cần tạo một response hoàn chỉnh. Nếu không giới hạn, server có thể tiêu thụ nhiều bộ nhớ và thời gian để gom kết quả.

Nên đưa giới hạn vào schema và service:

~~~graphql
type Query {
  books(first: Int = 20, after: String): BookConnection!
}
~~~

Một kiểu connection đơn giản:

~~~graphql
type BookConnection {
  edges: [BookEdge!]!
  pageInfo: PageInfo!
}

type BookEdge {
  cursor: String!
  node: Book!
}

type PageInfo {
  hasNextPage: Boolean!
  endCursor: String
}
~~~

Resolver có thể nhận first và after, xác thực giới hạn rồi gọi service để lấy đúng một trang:

~~~java
@QueryMapping
public Mono<BookConnection> books(
        @Argument Integer first,
        @Argument String after) {

    int pageSize = first == null ? 20 : first;

    if (pageSize < 1 || pageSize > 100) {
        return Mono.error(
                new IllegalArgumentException(
                        "first must be between 1 and 100"));
    }

    return bookService.findConnection(pageSize, after);
}
~~~

Giới hạn nên được kiểm tra cả ở tầng service hoặc tầng truy vấn dữ liệu để tránh client truyền giá trị quá lớn. Với cursor pagination, cursor cần ổn định và có thứ tự rõ ràng để tránh bỏ sót hoặc lặp phần tử giữa các trang.

## 11. Tránh fan-out không kiểm soát

Một Query có thể kích hoạt nhiều lời gọi service. Ví dụ, client yêu cầu 100 sách và mỗi sách lại phân giải author bằng một request riêng. Dù từng lời gọi là reactive, số lượng request vẫn có thể quá lớn.

Reactive giúp không phải giữ một thread chờ từng request, nhưng không tự giảm số lượng truy vấn hoặc tải backend.

Các hướng xử lý:

- Dùng @BatchMapping hoặc DataLoader để gom các lần tải dữ liệu liên quan.
- Giới hạn kích thước trang và số phần tử tối đa.
- Giới hạn concurrency khi dùng flatMap với một nguồn dữ liệu có quota.
- Dùng timeout phù hợp cho lời gọi service bên ngoài.
- Theo dõi thời gian và số lần gọi của từng resolver.
- Tránh truy vấn các field không cần thiết ở tầng database.

Ví dụ giới hạn concurrency:

~~~java
Flux<Author> authors = Flux.fromIterable(authorIds)
        .flatMap(authorService::findById, 8);
~~~

Tham số 8 giới hạn số inner publisher được xử lý đồng thời. Con số phù hợp cần dựa trên khả năng của service phía sau và tải thực tế.

Đối với quan hệ một-nhiều hoặc nhiều-một, hãy xem xét batch loading trước khi tăng concurrency. Tăng số request song song không thay thế việc loại bỏ N+1.

## 12. Reactive context và dữ liệu theo request

Trong reactive pipeline, dữ liệu theo request có thể được truyền qua Reactor Context hoặc GraphQLContext tùy điểm tích hợp.

Không lưu user hiện tại hoặc dữ liệu request vào field mutable của singleton controller/service. Nhiều GraphQL request có thể được xử lý đồng thời; state dùng chung dễ làm lẫn dữ liệu giữa người dùng.

Với annotated controller, có thể nhận dữ liệu từ GraphQL context bằng các cơ chế hỗ trợ như @ContextValue. Ví dụ:

~~~java
@QueryMapping
public Mono<List<Book>> myBooks(
        @ContextValue("currentUserId") String userId) {
    return bookService.findByOwnerId(userId).collectList();
}
~~~

Giá trị currentUserId cần được đưa vào GraphQL context bởi tầng xác thực hoặc interceptor thích hợp. Không tin dữ liệu định danh do client tự truyền nếu nghiệp vụ yêu cầu danh tính đã được xác thực.

Nếu dùng reactive security hoặc reactive transaction, cần bảo đảm các thành phần đó hoạt động trên cùng reactive chain và không bị ngắt bởi block() hoặc subscribe() thủ công.

## 13. Kiểm thử Query reactive bằng GraphQlTester

GraphQlTester cung cấp cách kiểm thử operation mà không cần client GraphQL bên ngoài. Với reactive controller, test có thể chờ quá trình thực thi hoàn tất rồi xác minh dữ liệu.

Ví dụ:

~~~java
@Test
void shouldReturnBookFromReactiveQuery() {
    graphQlTester.document("""
            query BookById($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
            .variable("id", "b-01")
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("b-01");
}
~~~

Nên kiểm thử các trường hợp:

1. Mono phát ra một giá trị.
2. Mono.empty() với field nullable.
3. Mono.empty() với field non-null.
4. Publisher phát lỗi và GraphQL response có errors phù hợp.
5. Flux phát nhiều phần tử và danh sách trả về đúng thứ tự.
6. Flux.empty() tạo danh sách rỗng cho field list non-null.
7. Query kết hợp nhiều service bằng zip hoặc flatMap.
8. Pagination từ chối giới hạn không hợp lệ.
9. Batch loading không tạo truy vấn N+1.
10. Context người dùng không bị dùng nhầm giữa các request.

Với test bất đồng bộ, hãy để GraphQlTester quản lý việc thực thi và chờ kết quả. Không cần gọi subscribe() thủ công trong test để kích hoạt controller.

## 14. Query reactive và Subscription khác nhau thế nào?

Cả Query và Subscription đều có thể sử dụng kiểu reactive trong Spring for GraphQL, nhưng ý nghĩa giao thức khác nhau.

| Tiêu chí | Query reactive | Subscription |
|---|---|---|
| Mục đích | Đọc dữ liệu tại thời điểm request | Nhận sự kiện hoặc cập nhật theo thời gian |
| Annotation | @QueryMapping | @SubscriptionMapping |
| Kiểu trả về thường gặp | Mono<T>, Flux<T> cho field list | Flux<T> |
| Kết quả phía client | Một GraphQL response cho operation | Luồng nhiều response/event |
| Kết thúc | Khi các field hoàn tất | Khi publisher hoàn tất hoặc client hủy |
| Ví dụ | Tìm danh sách sách | Nhận thông báo khi có sách mới |

Ví dụ Query:

~~~java
@QueryMapping
public Flux<Book> books() {
    return bookService.findAll();
}
~~~

Ví dụ Subscription:

~~~java
@SubscriptionMapping
public Flux<BookEvent> bookAdded() {
    return bookEventPublisher.events();
}
~~~

Ở Query, Flux được dùng để tạo kết quả list của field trong response. Ở Subscription, Flux đại diện cho các sự kiện được phát theo thời gian. Đừng dùng Query để mô phỏng push notification hoặc dùng Subscription chỉ để trả một danh sách thông thường.

## 15. Checklist triển khai Query reactive

Trước khi đưa resolver reactive vào ứng dụng:

- [ ] Kiểu SDL phù hợp với số lượng kết quả: object hay list.
- [ ] Mono và Flux được dùng đúng ngữ nghĩa.
- [ ] Controller trả publisher trực tiếp, không block hoặc subscribe thủ công.
- [ ] Reactive repository/client được dùng khi có thể.
- [ ] Tác vụ blocking được cô lập nếu chưa thể thay thế.
- [ ] Mono.empty và lỗi được xử lý theo nullability.
- [ ] Query list có giới hạn và pagination.
- [ ] Các lời gọi độc lập được kết hợp bằng toán tử reactive phù hợp.
- [ ] N+1 được xử lý bằng batch loading hoặc DataLoader.
- [ ] Timeout, concurrency và lỗi downstream có chính sách rõ ràng.
- [ ] Context và security không dùng state mutable dùng chung.
- [ ] Có test cho giá trị, empty, error và danh sách rỗng.

## Kết luận

Spring for GraphQL cho phép annotated controller trả về các reactive type như Mono và Flux cho Query. Mono phù hợp với field đơn, Flux phù hợp với field danh sách. Reactor cung cấp các toán tử như map, flatMap và zip để kết hợp dữ liệu từ nhiều nguồn mà không cần block thread.

Một Query trả về Flux vẫn là operation request-response với kết quả list; Subscription mới là cơ chế phát nhiều event theo thời gian. Để Query reactive vận hành tốt, cần tránh block và subscribe thủ công, xử lý empty/error theo nullability, giới hạn pagination và fan-out, đồng thời kiểm thử bằng GraphQlTester.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
