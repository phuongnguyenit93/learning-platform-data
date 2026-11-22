# Reactive resolver và backpressure

Trong Spring for GraphQL, resolver có thể trả về giá trị đồng bộ, CompletionStage hoặc kiểu reactive như Mono và Flux. Khi dùng đúng cách, reactive resolver giúp kết nối GraphQL với R2DBC, WebClient, message stream và các service bất đồng bộ. Backpressure giúp điều tiết lượng dữ liệu được phát từ nguồn tới subscriber, đặc biệt quan trọng với Subscription và các pipeline có luồng dữ liệu liên tục.

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích cách Spring for GraphQL chuyển Mono và Flux thành kết quả GraphQL.
- Chọn Mono hoặc Flux phù hợp với kiểu dữ liệu của field.
- Phân biệt Flux trong Query/Mutation với Flux trong Subscription.
- Hiểu backpressure, demand, request và cancellation trong Reactive Streams.
- Điều tiết concurrency, prefetch và buffer trong Reactor.
- Kết hợp reactive resolver với R2DBC, WebClient và DataLoader.
- Xử lý lỗi, timeout và cancellation trong reactive pipeline.
- Kiểm thử reactive resolver và Subscription bằng StepVerifier và GraphQlTester.
- Tránh các lỗi phổ biến như block(), subscribe() thủ công và buffer không giới hạn.

## 1. Reactive resolver trong Spring for GraphQL

GraphQL Java thực thi mỗi field thông qua DataFetcher. Spring for GraphQL cho phép controller method và DataFetcher trả về các kiểu reactive như Mono và Flux.

Ví dụ controller:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Mono<Book> bookById(@Argument String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public Flux<Book> latestBooks(@Argument int first) {
        return bookService.findLatest(first);
    }
}
~~~

Spring for GraphQL đăng ký các method được đánh dấu bằng @QueryMapping, @MutationMapping, @SubscriptionMapping và @SchemaMapping thành DataFetcher. Các method này có thể trả về giá trị trực tiếp, Mono, Flux hoặc một số kiểu bất đồng bộ khác.

Reactive resolver hữu ích khi dữ liệu đến từ:

- R2DBC hoặc một reactive repository.
- WebClient gọi service khác.
- Redis reactive client.
- Một message source hoặc event publisher.
- Pipeline Reactor cần kết hợp nhiều nguồn dữ liệu.

Reactive không tự làm cho một thao tác blocking trở thành non-blocking. Nếu service bên dưới dùng JDBC hoặc gọi HTTP blocking, chỉ bọc kết quả vào Mono không giúp giải phóng thread đang bị chặn.

## 2. Mono và Flux khác nhau thế nào?

Reactor cung cấp hai kiểu publisher thường dùng:

| Kiểu | Số phần tử | Ý nghĩa thường gặp |
|---|---:|---|
| Mono<T> | 0 hoặc 1 | Một object, kết quả tìm kiếm, một thao tác bất đồng bộ |
| Flux<T> | 0 đến N | Một danh sách, luồng sự kiện hoặc nhiều kết quả |

Ví dụ:

~~~java
Mono<Book> book = bookRepository.findById("b-01");

Flux<Book> books = bookRepository.findLatest();
~~~

Mono có thể hoàn tất mà không phát phần tử nào, phát một phần tử rồi hoàn tất, hoặc kết thúc bằng lỗi. Flux có thể phát nhiều phần tử theo thời gian rồi hoàn tất, hoặc kết thúc bằng lỗi.

Các kiểu này là cách biểu diễn kết quả trong Java. GraphQL SDL vẫn khai báo kiểu dữ liệu GraphQL thông thường:

~~~graphql
type Query {
  bookById(id: ID!): Book
  latestBooks(first: Int!): [Book!]!
}
~~~

Field bookById trả về một Book hoặc null. Field latestBooks trả về một list Book. SDL không có kiểu Mono hay Flux.

## 3. Spring for GraphQL chuyển reactive DataFetcher như thế nào?

GraphQlSource builder mặc định của Spring for GraphQL hỗ trợ DataFetcher trả về Mono và Flux.

Hành vi phụ thuộc operation:

- Với Query và Mutation thông thường, Mono được chuyển thành CompletableFuture cho GraphQL Java.
- Với Query và Mutation, Flux được thu thập thành List rồi chuyển thành CompletableFuture.
- Với Subscription, publisher được giữ dưới dạng Reactive Streams Publisher để phát nhiều GraphQL response theo thời gian.

Sự khác biệt này rất quan trọng. Một resolver Query trả Flux<Book> không có nghĩa HTTP response sẽ gửi từng Book ngay khi Book đó được phát. Spring for GraphQL thu thập các phần tử của Flux thành một List để tạo kết quả field, sau đó GraphQL trả response theo operation.

Ví dụ:

~~~java
@QueryMapping
public Flux<Book> latestBooks(@Argument int first) {
    return bookService.findLatest(first);
}
~~~

Với SDL:

~~~graphql
type Query {
  latestBooks(first: Int!): [Book!]!
}
~~~

Spring for GraphQL chờ Flux hoàn tất và tổng hợp các Book thành List trong GraphQL result. Client nhận một response chứa list, không phải một chuỗi response riêng cho từng Book.

Vì vậy, nếu cần giới hạn bộ nhớ, hãy giới hạn số phần tử bằng pagination hoặc take(). Không trả về một Flux vô hạn từ Query hoặc Mutation vì GraphQL sẽ phải chờ publisher hoàn tất để tạo List.

## 4. Dùng Mono cho Query và Mutation trả về một kết quả

Mono phù hợp khi field trả về tối đa một object hoặc một scalar.

Ví dụ service:

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

Controller:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Mono<Book> bookById(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

Với một Mutation, Mono cũng phù hợp nếu thao tác tạo hoặc cập nhật trả về một kết quả:

~~~java
@MutationMapping
public Mono<Book> addBook(@Argument BookInput input) {
    return bookService.addBook(input);
}
~~~

Không cần gọi block() để lấy Book trước khi return. GraphQL runtime sẽ chờ CompletionStage được tạo từ Mono và tiếp tục xây dựng response khi dữ liệu sẵn sàng.

Nếu Mono hoàn tất rỗng, field nullable có thể nhận giá trị null. Nếu SDL khai báo field non-null, việc trả null sẽ tạo GraphQL execution error và áp dụng null propagation theo schema.

## 5. Dùng Flux cho field list trong Query

Flux phù hợp với field có kiểu list khi dữ liệu được cung cấp theo dạng reactive stream.

~~~graphql
type Query {
  latestBooks(first: Int!): [Book!]!
}
~~~

~~~java
@QueryMapping
public Flux<Book> latestBooks(@Argument int first) {
    int pageSize = Math.min(Math.max(first, 1), 100);

    return bookService.findLatest(pageSize)
            .take(pageSize);
}
~~~

take(pageSize) giới hạn số phần tử mà pipeline phát ra. Khi đã nhận đủ số phần tử, publisher downstream sẽ hủy subscription upstream.

Dù nguồn dữ liệu là Flux, Spring for GraphQL vẫn thu thập kết quả thành List cho Query thông thường. Điều này có nghĩa:

- Flux có thể giúp đọc dữ liệu theo từng phần từ upstream.
- Các operator reactive có thể điều tiết việc yêu cầu dữ liệu.
- GraphQL response vẫn cần giữ list đã thu thập trước khi serialize.
- Bộ nhớ vẫn tăng theo số phần tử được trả về.

Không dùng Flux thay thế pagination. Với dữ liệu lớn, nên giới hạn page size ngay tại repository/database thay vì tải toàn bộ rồi mới take().

## 6. Subscription là trường hợp streaming

Subscription khác Query và Mutation. Một subscription đăng ký nhận các event theo thời gian, vì vậy publisher không cần hoàn tất sau một phần tử.

Schema:

~~~graphql
type Subscription {
  bookAdded: BookEvent!
}

type BookEvent {
  id: ID!
  book: Book!
  occurredAt: String!
}
~~~

Controller:

~~~java
@Controller
public class BookSubscriptionController {

    private final BookEventService eventService;

    public BookSubscriptionController(BookEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<BookEvent> bookAdded() {
        return eventService.events();
    }
}
~~~

Khi client đăng ký bookAdded, Spring for GraphQL giữ publisher và mỗi event được phát sẽ đi qua GraphQL execution để resolve các field được chọn.

Subscription cần một transport hỗ trợ streaming, chẳng hạn WebSocket hoặc HTTP Server-Sent Events (SSE). HTTP POST request-response thông thường không thể trả một chuỗi event liên tục.

Flux trong Subscription là một Reactive Streams Publisher thực sự. Nó có thể tiếp tục phát event cho đến khi nguồn hoàn tất, lỗi hoặc subscription bị hủy.

## 7. Backpressure là gì?

Backpressure là cơ chế để subscriber cho upstream biết mình sẵn sàng nhận bao nhiêu phần tử.

Trong Reactive Streams, subscriber yêu cầu dữ liệu bằng cách gọi request(n) trên Subscription:

- request(1): yêu cầu một phần tử.
- request(10): yêu cầu tối đa mười phần tử.
- request(Long.MAX_VALUE): yêu cầu không giới hạn, thường được gọi là unbounded demand.
- cancel(): hủy subscription và yêu cầu upstream dừng phát dữ liệu.

Backpressure giúp producer không phát dữ liệu nhanh hơn khả năng xử lý của consumer khi toàn bộ pipeline hỗ trợ cơ chế demand.

Ví dụ một nguồn phát 1.000 event nhưng consumer chỉ yêu cầu từng phần tử:

~~~java
Flux<Integer> numbers = Flux.range(1, 1_000)
        .doOnRequest(n ->
                log.debug("Upstream received demand: {}", n));
~~~

Khi subscriber yêu cầu 5 phần tử, upstream có thể phát 5 phần tử rồi chờ demand tiếp theo.

Backpressure không phải một bộ giới hạn tốc độ cố định. Nó là tín hiệu demand được truyền qua chuỗi publisher/subscriber. Mỗi operator có thể thay đổi cách yêu cầu dữ liệu, buffer hoặc prefetch.

## 8. Backpressure trong Query khác Subscription

Cần phân biệt hai trường hợp:

**Query và Mutation**

Spring for GraphQL thu thập Flux thành List trước khi hoàn tất GraphQL response. Client nhận một JSON response hoàn chỉnh cho operation. Client HTTP không thể yêu cầu server chỉ gửi thêm 5 phần tử của cùng một list sau khi đã nhận một phần response.

Nếu Query trả về một Flux rất lớn, việc thu thập thành List có thể tiêu tốn nhiều bộ nhớ. Backpressure bên trong Reactor pipeline có thể điều tiết upstream, nhưng không biến GraphQL Query thành response stream.

**Subscription**

Publisher của Subscription được giữ lại để phát nhiều GraphQL response. Khi transport tiêu thụ event, demand và cancellation có thể được truyền qua Reactive Streams publisher.

Tuy nhiên, khả năng điều tiết thực tế còn phụ thuộc transport, event source và các operator trong pipeline. Một broker hoặc hot source có thể không thể giảm tốc độ phát theo demand của subscriber. Khi đó cần chính sách buffer, drop, latest hoặc giới hạn tốc độ phù hợp với nghiệp vụ.

## 9. Backpressure đi qua pipeline như thế nào?

Một reactive pipeline thường có nhiều thành phần:

~~~text
Database / Event source
        |
        v
Repository Publisher
        |
        v
Service operators
        |
        v
GraphQL DataFetcher
        |
        v
GraphQL execution
        |
        v
HTTP streaming transport
        |
        v
Client subscriber
~~~

Khi client hoặc transport yêu cầu ít event hơn, tín hiệu demand có thể truyền ngược qua các publisher tới nguồn dữ liệu, nếu từng tầng hỗ trợ Reactive Streams.

Ví dụ với Subscription:

1. Event source tạo publisher.
2. GraphQL đăng ký vào publisher.
3. Mỗi event được resolve thành GraphQL result.
4. Transport gửi result cho client.
5. Subscriber yêu cầu thêm event hoặc hủy subscription.
6. Demand/cancellation được truyền ngược qua pipeline khi các tầng hỗ trợ.

Nếu một tầng chuyển dữ liệu sang API blocking hoặc tự subscribe độc lập, tín hiệu demand có thể bị mất ở ranh giới đó.

## 10. Điều tiết concurrency với flatMap và concatMap

flatMap cho phép xử lý nhiều phần tử đồng thời. Điều này hữu ích khi mỗi phần tử cần gọi một service bất đồng bộ, nhưng concurrency không giới hạn có thể gây áp lực lên connection pool hoặc downstream.

Ví dụ giới hạn tối đa 8 lời gọi đồng thời:

~~~java
Flux<BookDetails> details = bookRepository.findLatest()
        .flatMap(bookService::loadDetails, 8);
~~~

Concurrency giới hạn số inner publisher được xử lý đồng thời. Khi downstream chậm, Reactor cũng điều chỉnh demand theo pipeline, nhưng cần xem xét prefetch và buffer của các operator.

Nếu cần xử lý tuần tự, dùng concatMap:

~~~java
Flux<BookResult> results = bookRepository.findPending()
        .concatMap(bookService::process);
~~~

concatMap chỉ xử lý inner publisher theo thứ tự, giúp giảm số tác vụ đồng thời và giữ thứ tự phát kết quả. Đổi lại throughput có thể thấp hơn flatMap.

| Operator | Đặc điểm | Khi dùng |
|---|---|---|
| flatMap(mapper, concurrency) | Xử lý nhiều inner publisher đồng thời | Gọi nhiều service độc lập |
| concatMap(mapper) | Xử lý lần lượt, giữ thứ tự | Tác vụ phụ thuộc thứ tự |
| flatMapSequential(mapper, concurrency) | Xử lý đồng thời nhưng phát kết quả theo thứ tự nguồn | Cần concurrency và giữ thứ tự |

Không tăng concurrency chỉ để tăng throughput. Hãy đo giới hạn của database pool, HTTP connection pool và downstream service.

## 11. Điều tiết demand bằng limitRate

limitRate chia demand từ downstream thành các đợt request nhỏ hơn tới upstream.

Ví dụ:

~~~java
Flux<Book> books = bookRepository.findAll()
        .limitRate(64);
~~~

Operator này có thể giúp tránh yêu cầu một lượng dữ liệu quá lớn cùng lúc từ upstream. Tuy nhiên, nó không giới hạn tổng số phần tử của Flux và cũng không tự tạo pagination ở database.

Nếu cần giới hạn tổng số phần tử, dùng take(n):

~~~java
Flux<Book> firstHundred = bookRepository.findAll()
        .take(100);
~~~

Phân biệt:

- limitRate(64): điều tiết cách yêu cầu dữ liệu theo từng đợt.
- take(100): chỉ cho phép tối đa 100 phần tử đi tiếp.
- Pagination: yêu cầu nguồn dữ liệu chỉ tải một trang có giới hạn.

Trong GraphQL Query, pagination ở repository/database thường là lựa chọn quan trọng nhất để kiểm soát kích thước List cuối cùng.

## 12. Buffer và chiến lược khi producer nhanh hơn consumer

Một số nguồn dữ liệu là hot publisher hoặc event source không thể chờ demand của subscriber. Ví dụ, thiết bị gửi telemetry liên tục hoặc hệ thống nhận event từ broker.

Khi producer nhanh hơn consumer, cần chọn chính sách:

| Chiến lược | Hành vi | Phù hợp |
|---|---|---|
| Buffer có giới hạn | Giữ event trong một hàng đợi tối đa | Burst ngắn, cần giữ event |
| Drop | Bỏ event khi downstream chưa sẵn sàng | Metric hoặc telemetry có thể mất |
| Latest | Chỉ giữ giá trị mới nhất | Trạng thái hiện tại, dashboard |
| Error khi overflow | Báo lỗi và hủy nguồn khi buffer đầy | Muốn phát hiện quá tải rõ ràng |

Ví dụ buffer có giới hạn:

~~~java
Flux<BookEvent> events = eventSource.events()
        .onBackpressureBuffer(
                256,
                overflowEvent -> log.warn(
                        "Event buffer overflow: {}", overflowEvent));
~~~

Overload có maxSize yêu cầu unbounded demand từ upstream rồi giữ tối đa 256 event tại ranh giới operator khi downstream chưa sẵn sàng. Khi vượt capacity, callback overflow được gọi và upstream bị hủy kèm lỗi overflow. Vì vậy, buffer có giới hạn bảo vệ bộ nhớ nhưng không làm producer chậm lại; nó chỉ hấp thụ burst trong phạm vi đã đặt. Không dùng buffer vô hạn cho event stream dài hạn vì bộ nhớ có thể tăng không giới hạn.

Ví dụ drop event:

~~~java
Flux<MetricEvent> metrics = metricSource.events()
        .onBackpressureDrop(event ->
                log.debug("Dropping metric event {}", event.id()));
~~~

Operator drop cũng yêu cầu unbounded demand từ upstream rồi bỏ các phần tử khi downstream chưa có demand. Chỉ dùng drop nếu nghiệp vụ chấp nhận mất event. Với đơn hàng, thanh toán hoặc sự kiện audit, việc drop có thể làm sai dữ liệu nghiệp vụ.

## 13. Tránh tạo unbounded demand ngoài ý muốn

Một số cách subscribe phổ biến yêu cầu unbounded demand ngay lập tức, ví dụ:

- subscribe() và nhiều biến thể lambda.
- block(), blockFirst(), blockLast().
- Duyệt toIterable() hoặc toStream().

Vì vậy, không nên gọi các phương thức này tùy tiện trong reactive resolver.

Ví dụ không nên làm:

~~~java
@QueryMapping
public Book bookById(@Argument String id) {
    return bookService.findById(id).block();
}
~~~

Cách này chặn thread đang xử lý GraphQL request, làm mất lợi ích non-blocking và có thể gây cạn thread khi tải tăng.

Cũng không nên tự subscribe bên trong controller:

~~~java
@QueryMapping
public String refresh() {
    bookService.refresh().subscribe();
    return "started";
}
~~~

GraphQL engine không còn kiểm soát lifecycle của publisher này. Nó không thể chờ kết quả, quản lý lỗi hoặc truyền cancellation theo request.

Hãy trả publisher trực tiếp:

~~~java
@MutationMapping
public Mono<Book> refreshBook(@Argument String id) {
    return bookService.refresh(id);
}
~~~

Framework sẽ subscribe và chờ theo lifecycle của GraphQL operation.

## 14. Kết hợp reactive resolver với R2DBC

R2DBC cung cấp API truy cập relational database theo mô hình reactive. Repository có thể trả Mono hoặc Flux.

Ví dụ:

~~~java
public interface BookRepository
        extends ReactiveCrudRepository<Book, String> {

    Flux<Book> findByPublishedYearGreaterThan(int year);
}
~~~

Service:

~~~java
@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Flux<Book> findRecentBooks(int year) {
        return repository.findByPublishedYearGreaterThan(year)
                .limitRate(32);
    }
}
~~~

Controller:

~~~java
@QueryMapping
public Flux<Book> recentBooks(@Argument int year) {
    return bookService.findRecentBooks(year);
}
~~~

R2DBC có thể hỗ trợ demand ở tầng driver và publisher. Tuy nhiên, nếu GraphQL Query thu Flux thành List, toàn bộ kết quả cuối cùng vẫn được giữ để serialize response.

Với tập dữ liệu lớn, hãy kết hợp R2DBC với pagination và page size tối đa. Không dùng findAll() cho một GraphQL field công khai nếu số lượng bản ghi không được kiểm soát.

## 15. Kết hợp reactive resolver với WebClient

WebClient trả về Mono hoặc Flux và phù hợp khi resolver cần gọi service HTTP khác.

Ví dụ:

~~~java
@Service
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<Inventory> findInventory(String bookId) {
        return webClient.get()
                .uri("/inventory/{bookId}", bookId)
                .retrieve()
                .bodyToMono(Inventory.class);
    }
}
~~~

Resolver:

~~~java
@Controller
public class BookInventoryController {

    private final InventoryClient inventoryClient;

    public BookInventoryController(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @SchemaMapping(typeName = "Book", field = "inventory")
    public Mono<Inventory> inventory(Book book) {
        return inventoryClient.findInventory(book.id());
    }
}
~~~

GraphQL engine chờ Mono hoàn tất để điền field inventory. Không cần block() để lấy response từ WebClient.

Nếu query trả về nhiều Book và mỗi Book gọi inventory service riêng, có thể phát sinh nhiều HTTP request. Hãy cân nhắc batch endpoint, DataLoader, cache hoặc giới hạn concurrency để tránh tạo tải lớn lên downstream.

## 16. Kết hợp DataLoader và reactive batch mapping

Spring for GraphQL hỗ trợ reactive return types trong @BatchMapping. Method có thể trả về Mono<Map<K,V>> hoặc Flux<V>.

Ví dụ:

~~~java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::authorId)
                .distinct()
                .toList();

        return authorService.findAllByIds(authorIds)
                .map(authors -> mapAuthors(books, authors));
    }
}
~~~

Batch mapping gom nhiều parent Book vào một lần xử lý. Publisher trả về Map ánh xạ mỗi Book với Author tương ứng.

Nếu method trả Flux<V>, thứ tự các giá trị phải khớp với thứ tự các parent objects được truyền vào batch method. Nếu thứ tự không khớp, Author có thể bị gán nhầm cho Book.

Reactive DataLoader giúp tránh chặn thread trong khi chờ batch query, còn DataLoader batching giảm số lần gọi backend. Hai mục tiêu này bổ sung cho nhau.

## 17. Cancellation và timeout

Cancellation xảy ra khi consumer không còn cần dữ liệu. Ví dụ:

- Client đóng kết nối Subscription.
- Request GraphQL bị timeout.
- Pipeline dùng take(n) đã nhận đủ phần tử.
- Downstream hủy subscription.

Một reactive pipeline nên truyền cancellation tới nguồn dữ liệu để dừng công việc không còn cần thiết.

Ví dụ:

~~~java
Flux<BookEvent> events = eventService.events()
        .doOnCancel(() ->
                log.info("Book subscription cancelled"));
~~~

Spring for GraphQL cung cấp TimeoutWebGraphQlInterceptor cho web transports. Khi request vượt thời gian cấu hình, interceptor gửi tín hiệu cancel lên chain và reactive DataFetcher có thể tự động hủy công việc đang chạy.

Cấu hình Spring Boot:

~~~java
@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(
                Duration.ofSeconds(5));
    }
}
~~~

Timeout request và timeout Subscription không nhất thiết có cùng ý nghĩa. Một Subscription hợp lệ có thể tồn tại lâu, nên cần cấu hình timeout phù hợp với transport và chính sách kết nối thay vì áp một request timeout ngắn cho toàn bộ stream.

Cancellation chỉ hiệu quả nếu publisher và nguồn dữ liệu phản ứng với cancel. Một tác vụ blocking không thể bị dừng an toàn chỉ vì downstream đã hủy publisher.

## 18. Xử lý lỗi trong reactive pipeline

Lỗi trong Mono hoặc Flux được truyền dưới dạng error signal. Spring for GraphQL chuyển lỗi của DataFetcher thành GraphQL errors thông qua DataFetcherExceptionResolver.

Có thể ánh xạ lỗi nghiệp vụ trước khi trả publisher:

~~~java
@QueryMapping
public Mono<Book> bookById(@Argument String id) {
    return bookService.findById(id)
            .switchIfEmpty(Mono.error(
                    new BookNotFoundException(id)));
}
~~~

Có thể dùng onErrorMap để đổi lỗi kỹ thuật thành lỗi domain:

~~~java
public Mono<Book> findBook(String id) {
    return repository.findById(id)
            .onErrorMap(
                    DataAccessException.class,
                    ex -> new BookServiceException(
                            "Unable to load book", ex));
}
~~~

Dùng onErrorResume khi có fallback hợp lệ:

~~~java
public Mono<BookRecommendation> recommendations(String bookId) {
    return recommendationClient.find(bookId)
            .onErrorResume(
                    RecommendationUnavailableException.class,
                    ex -> Mono.just(BookRecommendation.empty()));
}
~~~

Không dùng onErrorResume để âm thầm biến mọi lỗi thành dữ liệu rỗng. Cách đó có thể che giấu lỗi hệ thống và làm client hiểu sai kết quả.

Với Subscription, lỗi có thể xảy ra sau khi publisher đã được tạo và client đã đăng ký. DataFetcherExceptionResolver không xử lý được các error signal phát sinh sau thời điểm DataFetcher trả publisher. Spring for GraphQL cung cấp SubscriptionExceptionResolver để ánh xạ lỗi của subscription publisher thành GraphQL errors gửi qua transport.

## 19. Giữ pipeline non-blocking và quản lý Scheduler

Một reactive pipeline chỉ thực sự non-blocking khi các thao tác bên trong không chặn thread.

Nếu dùng R2DBC hoặc WebClient, thường không cần tự chuyển scheduler cho mỗi request. Các thư viện này đã sử dụng non-blocking I/O.

Nếu bắt buộc gọi một thư viện blocking, có thể cô lập công việc trên boundedElastic:

~~~java
Mono<Book> book = Mono.fromCallable(
                () -> legacyBookService.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Không chạy JDBC hoặc file I/O blocking trực tiếp trên event-loop của WebFlux. Đồng thời, không dùng boundedElastic để che giấu một thiết kế blocking không có giới hạn; cần theo dõi queue và số thread.

Một số nguyên tắc:

- Không gọi block() trong resolver.
- Không gọi subscribe() để tách công việc khỏi GraphQL lifecycle.
- Không dùng publishOn hoặc subscribeOn tùy tiện cho mọi pipeline.
- Giới hạn concurrency khi gọi downstream.
- Dùng timeout cho I/O có thể treo.
- Bảo đảm context propagation khi chuyển scheduler.
- Nếu ứng dụng imperative dùng JDBC, cân nhắc model đồng bộ có executor hoặc virtual threads thay vì giả lập reactive bằng cách bọc blocking call.

## 20. Context propagation trong reactive resolver

Với WebFlux, Spring for GraphQL hỗ trợ truyền Reactor Context từ transport layer tới reactive DataFetcher. Context có thể chứa security context, tracing context hoặc metadata được WebGraphQlInterceptor bổ sung.

Ví dụ lấy context trong Reactor pipeline:

~~~java
public Mono<Book> currentBook(String id) {
    return Mono.deferContextual(contextView -> {
        String tenantId = contextView.get("tenantId");

        return bookService.findByTenantAndId(tenantId, id);
    });
}
~~~

Context key phải được thiết lập ở interceptor hoặc thành phần phù hợp trước khi resolver sử dụng.

Không truyền user ID hoặc tenant ID qua GraphQL variables rồi xem đó là danh tính đáng tin cậy. Context xác thực cần đến từ security mechanism của request.

Nếu dùng publishOn hoặc subscribeOn, cần kiểm tra context propagation với thư viện và cấu hình hiện tại. Reactor Context gắn với subscription, không phải ThreadLocal thông thường.

## 21. Subscription có thể phát event không đúng thứ tự

Trong GraphQL Subscription, mỗi event được resolve thành một GraphQL response. Các field trong event có thể được fetch bất đồng bộ. Vì vậy, khi nhiều event đang được xử lý, response có thể được gửi qua transport không theo đúng thứ tự event ban đầu.

Spring for GraphQL cho phép bật cấu hình:

~~~java
SubscriptionExecutionStrategy.KEEP_SUBSCRIPTION_EVENTS_ORDERED
~~~

để buffer event và giữ thứ tự upstream.

Có thể đặt flag trong GraphQLContext bằng custom Instrumentation:

~~~java
public class SubscriptionOrderInstrumentation
        extends SimplePerformantInstrumentation {

    @Override
    public InstrumentationContext<ExecutionResult> beginExecution(
            InstrumentationExecutionParameters parameters,
            InstrumentationState state) {

        parameters.getGraphQLContext().put(
                SubscriptionExecutionStrategy.KEEP_SUBSCRIPTION_EVENTS_ORDERED,
                true);

        return SimpleInstrumentationContext.noOp();
    }
}
~~~

Giữ thứ tự có thể cần buffer các event đã hoàn tất xử lý field nhưng đang chờ event trước đó. Điều này làm tăng độ trễ và bộ nhớ khi một event xử lý chậm. Chỉ bật khi thứ tự event là yêu cầu nghiệp vụ.

Nếu event độc lập và client không yêu cầu thứ tự, để GraphQL xử lý theo khả năng hoàn tất có thể giúp giảm thời gian chờ.

## 22. Kiểm thử backpressure bằng StepVerifier

StepVerifier cho phép kiểm thử publisher mà không cần tự viết Subscriber.

Ví dụ kiểm tra demand:

~~~java
@Test
void shouldRespectRequestedDemand() {
    Flux<Integer> source = Flux.range(1, 5)
            .doOnRequest(n ->
                    log.info("Requested: {}", n));

    StepVerifier.create(source, 0)
            .thenRequest(2)
            .expectNext(1, 2)
            .thenCancel()
            .verify();
}
~~~

Test bắt đầu với demand bằng 0, sau đó yêu cầu 2 phần tử và hủy subscription. Đây là cách kiểm tra publisher phản ứng với request và cancel.

Có thể kiểm tra resolver trả Mono:

~~~java
@Test
void shouldReturnBookAsynchronously() {
    StepVerifier.create(bookService.findById("b-01"))
            .assertNext(book ->
                    assertThat(book.id()).isEqualTo("b-01"))
            .verifyComplete();
}
~~~

StepVerifier phù hợp để kiểm tra service publisher, cancellation, timeout, error và demand. Nó không tự chứng minh GraphQL HTTP transport đang stream Query response; cần kiểm tra transport riêng.

## 23. Kiểm thử GraphQL Subscription

GraphQlTester hỗ trợ thực thi Subscription qua executeSubscription(). Kết quả có thể được chuyển thành Flux để dùng StepVerifier.

Ví dụ:

~~~java
@Test
void shouldReceiveBookEvents() {
    Flux<BookEvent> events = graphQlTester.document("""
            subscription {
                bookAdded {
                    id
                    book {
                        id
                        title
                    }
                }
            }
            """)
            .executeSubscription()
            .toFlux("bookAdded", BookEvent.class);

    StepVerifier.create(events)
            .expectNextMatches(event ->
                    event.book().id().equals("b-01"))
            .thenCancel()
            .verify();
}
~~~

Test cần một Subscription source có thể điều khiển trong fixture. Sau khi phát event test, StepVerifier xác nhận event được nhận; thenCancel() kiểm tra việc hủy luồng.

Với transport integration test, cần cấu hình WebSocket hoặc SSE tương ứng. ExecutionGraphQlServiceTester có thể hữu ích để kiểm tra GraphQL execution mà không kiểm tra network transport.

## 24. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Query không hoàn tất | Resolver trả Flux không bao giờ complete | Dùng Query hữu hạn; dành publisher vô hạn cho Subscription |
| Query trả list quá lớn | Flux được aggregate thành List | Pagination và giới hạn page size |
| Thread bị chặn | Gọi block() hoặc dùng JDBC trực tiếp | Giữ publisher hoặc cô lập blocking work |
| Resolver chạy dù client đã hủy | Tự subscribe trong controller hoặc nguồn không hỗ trợ cancel | Trả publisher trực tiếp và kiểm tra cancellation |
| Memory tăng khi Subscription chậm | Buffer không giới hạn hoặc producer nhanh hơn consumer | Dùng buffer có giới hạn và chính sách overflow |
| Mất event | Dùng onBackpressureDrop không phù hợp | Chọn buffer, retry hoặc durable broker theo nghiệp vụ |
| Nhiều request downstream đồng thời | flatMap không giới hạn concurrency | Dùng flatMap với concurrency phù hợp |
| Kết quả list không đúng thứ tự | Dùng flatMap hoặc batch Flux không giữ thứ tự | Dùng concatMap, flatMapSequential hoặc mapping theo key |
| Subscription event sai thứ tự | Nested fields hoàn tất bất đồng bộ | Bật KEEP_SUBSCRIPTION_EVENTS_ORDERED khi cần |
| Lỗi subscription không được ánh xạ | Error xảy ra sau khi publisher được trả về | Cấu hình SubscriptionExceptionResolver |
| Context bị mất | Chuyển scheduler hoặc dùng ThreadLocal trong reactive chain | Dùng Reactor Context và kiểm tra context propagation |
| Backpressure không tới nguồn | Có tầng blocking hoặc publisher không tuân thủ Reactive Streams | Kiểm tra từng ranh giới và nguồn phát |

## 25. Checklist triển khai reactive resolver

Trước khi đưa reactive resolver vào production:

- [ ] Dùng Mono cho kết quả 0..1 và Flux cho 0..N.
- [ ] SDL khai báo kiểu GraphQL thực, không dùng Mono/Flux trong schema.
- [ ] Hiểu Flux của Query/Mutation được aggregate thành List.
- [ ] Không trả Flux vô hạn từ Query hoặc Mutation.
- [ ] Dùng Subscription cho luồng event liên tục.
- [ ] Subscription transport hỗ trợ WebSocket hoặc SSE.
- [ ] Giới hạn page size và số phần tử của Query.
- [ ] Kiểm soát concurrency và prefetch trong pipeline.
- [ ] Không dùng buffer vô hạn cho nguồn phát liên tục.
- [ ] Chọn chính sách overflow phù hợp nghiệp vụ.
- [ ] Không gọi block() hoặc subscribe() thủ công trong resolver.
- [ ] Cô lập blocking I/O nếu không thể thay bằng reactive driver.
- [ ] Có timeout và xử lý cancellation.
- [ ] Có xử lý lỗi cho cả DataFetcher và Subscription publisher.
- [ ] Kiểm tra context propagation.
- [ ] Kiểm thử demand, cancellation và event stream bằng StepVerifier.
- [ ] Đo memory, latency và tốc độ phát event khi tải tăng.

## Kết luận

Reactive resolver cho phép Spring for GraphQL làm việc với Mono, Flux và các nguồn dữ liệu bất đồng bộ. Mono phù hợp với một kết quả; Flux phù hợp với nhiều kết quả hoặc một luồng event. Tuy nhiên, Flux trong Query và Mutation được Spring for GraphQL thu thập thành List, trong khi Flux của Subscription được giữ như Reactive Streams Publisher để stream nhiều GraphQL response.

Backpressure điều tiết demand giữa subscriber và upstream. Để tận dụng nó, cần kiểm soát concurrency, prefetch, buffer và cancellation trên toàn pipeline. Hãy kết hợp reactive resolver với pagination, DataLoader, timeout và chính sách overflow phù hợp. Tránh block(), subscribe() thủ công và nguồn phát không giới hạn để giữ GraphQL execution ổn định khi tải tăng.

## Tài liệu tham khảo

- [Spring for GraphQL — Request Execution, Reactive DataFetcher](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Subscriptions](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Reactive Streams — Specification](https://www.reactive-streams.org/)
