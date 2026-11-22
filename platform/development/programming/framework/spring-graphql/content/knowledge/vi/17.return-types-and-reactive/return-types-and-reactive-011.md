# Async return và error

Trong Spring for GraphQL, một resolver không nhất thiết phải trả dữ liệu ngay tại thời điểm method được gọi. Nó có thể trả về một kết quả sẽ hoàn thành sau, chẳng hạn `Mono<T>`, `Flux<T>` hoặc `CompletionStage<T>`. GraphQL Java phối hợp các kết quả bất đồng bộ để tiếp tục phân giải cây field và tạo response khi các công việc cần thiết hoàn tất.

Khi một tác vụ bất đồng bộ thất bại, lỗi phải được chuyển thành GraphQL error. Spring for GraphQL cung cấp các extension point như `@GraphQlExceptionHandler`, `DataFetcherExceptionResolver` và `SubscriptionExceptionResolver` để xử lý lỗi theo đúng giai đoạn thực thi. Việc chọn đúng kiểu trả về và đúng cơ chế xử lý lỗi giúp API giữ được khả năng trả partial data, quản lý cancellation và tránh để lộ thông tin nội bộ.

Bài học này giải thích các kiểu return bất đồng bộ trong annotated controllers và DataFetcher, cách `Mono` và `Flux` được GraphQL xử lý, cách lỗi đi qua response, cách xử lý exception cho field và Subscription, cùng timeout, context propagation và kiểm thử.

## 1. Đồng bộ và bất đồng bộ trong resolver

Resolver đồng bộ trả về giá trị trực tiếp:

```java
@QueryMapping
public Book bookById(@Argument String id) {
    return bookService.findById(id);
}
```

Method chỉ trả về sau khi `bookService.findById` hoàn tất. Nếu service gọi database bằng API blocking, thread thực thi phải chờ thao tác đó.

Resolver bất đồng bộ trả về một handle đại diện cho công việc sẽ hoàn tất sau:

```java
@QueryMapping
public Mono<Book> bookById(@Argument String id) {
    return bookService.findByIdReactive(id);
}
```

Method trả về `Mono<Book>` ngay. Giá trị `Book` sẽ được phát ra sau khi nguồn dữ liệu hoàn thành. GraphQL engine có thể tiếp tục điều phối các field khác và đợi kết quả bất đồng bộ trước khi hoàn tất response.

Khác biệt cốt lõi:

| Cách trả về | Ý nghĩa |
| --- | --- |
| `T` | Giá trị đã có sẵn tại thời điểm method trả về |
| `Mono<T>` | Một giá trị bất đồng bộ hoặc không có giá trị |
| `Flux<T>` | Một chuỗi nhiều giá trị bất đồng bộ |
| `CompletionStage<T>` | Một kết quả Java sẽ hoàn thành trong tương lai |
| `Callable<T>` | Công việc đồng bộ được thực thi bất đồng bộ qua Executor đã cấu hình |

Không phải cứ dùng kiểu bất đồng bộ là code tự động nhanh hơn. Lợi ích phụ thuộc vào nguồn I/O, thread model và cách ứng dụng phối hợp công việc. Bọc một lời gọi blocking trong `Mono.just(...)` không làm lời gọi đó trở thành non-blocking.

## 2. Các kiểu return được Spring for GraphQL hỗ trợ

Với annotated controller methods, Spring for GraphQL hỗ trợ các kiểu return chính sau:

| Kiểu trả về | Ý nghĩa |
| --- | --- |
| `T` | Giá trị ứng dụng đã được phân giải |
| `Mono<T>` | Kết quả bất đồng bộ có tối đa một phần tử |
| `Flux<T>` | Nhiều kết quả bất đồng bộ |
| Kotlin `suspend fun` / `Flow` | Được tự động chuyển đổi tương ứng sang reactive types |
| `Callable<T>` | Chạy công việc qua Executor của `AnnotatedControllerConfigurer` |
| `DataFetcherResult<P>` | Kết quả GraphQL đầy đủ, có thể kèm errors, extensions hoặc local context |

Ở tầng GraphQL Java, `DataFetcher` có thể trả về `CompletionStage`; Spring for GraphQL hỗ trợ cơ chế này và dùng nó để thực thi field bất đồng bộ. `CompletableFuture` là một implementation phổ biến của `CompletionStage`. Với annotated controllers, `Mono`/`Flux` là lựa chọn reactive tự nhiên; `Callable` phù hợp cho công việc blocking cần đưa sang Executor.

### Trả về CompletableFuture

Khi tích hợp một DataFetcher cấp thấp hoặc một API Java đã cung cấp `CompletionStage`, có thể trả về `CompletableFuture`:

```java
DataFetcher<CompletableFuture<Book>> bookFetcher =
        environment -> CompletableFuture.supplyAsync(
                () -> bookService.findById(environment.getArgument("id")),
                executor);
```

Nên truyền Executor phù hợp thay vì mặc định dùng common pool cho mọi công việc. Nếu ứng dụng dùng annotated controllers, hãy chọn kiểu return được Spring hỗ trợ rõ ràng theo phiên bản đang sử dụng.

## 3. Mono<T>: một kết quả bất đồng bộ

`Mono<T>` phù hợp với field trả về một object hoặc scalar:

```java
@Controller
public class BookQueryController {

    private final ReactiveBookService bookService;

    public BookQueryController(ReactiveBookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Mono<Book> bookById(@Argument String id) {
        return bookService.findById(id);
    }
}
```

Một `Mono<Book>` có thể:

- Phát ra đúng một `Book` rồi complete.
- Complete mà không phát ra phần tử.
- Kết thúc bằng error signal.

Với field GraphQL nullable, Mono empty thường được biểu diễn thành `null`. Nếu SDL khai báo field non-null mà không có giá trị, GraphQL áp dụng quy tắc null propagation và tạo execution error phù hợp.

Không nên gọi `block()` trong resolver WebFlux chỉ để lấy giá trị từ Mono. Làm vậy sẽ chặn thread và triệt tiêu lợi ích của reactive pipeline.

## 4. Flux<T>: nhiều kết quả bất đồng bộ

`Flux<T>` phù hợp khi nguồn dữ liệu phát ra nhiều phần tử:

```java
@QueryMapping
public Flux<Book> books() {
    return bookService.findAll();
}
```

Với một field Query thông thường, Spring for GraphQL chuyển reactive DataFetcher return value sang dạng bất đồng bộ mà GraphQL Java có thể xử lý. Cụ thể, `Mono` được chuyển thành `CompletableFuture`; các phần tử của `Flux` được gom thành một `List` trước khi field hoàn tất.

Do đó, `Flux<Book>` trong một Query không có nghĩa HTTP response sẽ gửi từng cuốn sách ngay khi phần tử xuất hiện. Client thường nhận một GraphQL response sau khi danh sách field đã được tổng hợp.

Ví dụ SDL:

```graphql
type Query {
  books: [Book!]!
}
```

Controller:

```java
@QueryMapping
public Flux<Book> books() {
    return bookService.findAll();
}
```

GraphQL response vẫn có dạng danh sách:

```json
{
  "data": {
    "books": [
      { "id": "book-1", "title": "GraphQL Basics" },
      { "id": "book-2", "title": "Spring GraphQL" }
    ]
  }
}
```

Nếu danh sách có thể rất lớn, hãy thiết kế pagination thay vì dựa vào một Flux không giới hạn để trả toàn bộ dữ liệu trong một response.

## 5. Flux trong Subscription khác Flux trong Query

Subscription là operation dành cho dữ liệu phát sinh theo thời gian. Trong trường hợp này, `Flux<T>` có thể được giữ như Reactive Streams Publisher để transport gửi các event theo từng lần phát ra.

SDL:

```graphql
type Subscription {
  bookPublished: Book!
}
```

Controller:

```java
@Controller
public class BookSubscriptionController {

    private final BookEventService eventService;

    public BookSubscriptionController(BookEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<Book> bookPublished() {
        return eventService.bookPublished();
    }
}
```

Client mở subscription:

```graphql
subscription {
  bookPublished {
    id
    title
  }
}
```

Với Query thông thường, Flux được gom thành danh sách. Với Subscription, publisher được giữ để transport nhận các event liên tục. Vì vậy, hãy chọn operation type dựa trên hợp đồng API:

| Nhu cầu | Cách biểu diễn |
| --- | --- |
| Lấy danh sách hiện có | Query trả về List hoặc Flux |
| Theo dõi event mới | Subscription trả về Flux |
| Lấy một object bất đồng bộ | Query trả về Mono |

Subscription cần transport hỗ trợ streaming như WebSocket hoặc RSocket. HTTP POST thông thường không thể giữ một response stream subscription theo cách đó.

GraphQL có thể phân giải các field của từng event bất đồng bộ. Vì vậy, nếu các event được xử lý song song ở các tầng field, thứ tự event đi ra transport có thể khác thứ tự upstream. Khi ứng dụng yêu cầu giữ thứ tự, có thể cấu hình tùy chọn giữ thứ tự subscription event qua GraphQL context theo hướng dẫn của phiên bản GraphQL Java đang dùng.

## 6. Callable và thực thi code blocking

Nếu service hiện tại dùng JDBC hoặc API blocking, không nên gọi trực tiếp từ event-loop thread của WebFlux. Một lựa chọn là dùng `Callable<T>` với Executor được cấu hình trên `AnnotatedControllerConfigurer`:

```java
@SchemaMapping
public Callable<BookDetails> details(Book book) {
    return () -> blockingBookService.loadDetails(book.id());
}
```

Spring for GraphQL gửi Callable tới Executor đã cấu hình. Nếu không cấu hình Executor, không nên giả định Callable tự động chạy trên background thread.

Với Java 21+, khi `AnnotatedControllerConfigurer` có Executor, các controller method có chữ ký blocking có thể được gọi bất đồng bộ. Spring Boot có thể tự cấu hình Executor dùng virtual threads khi bật:

```yaml
spring:
  threads:
    virtual:
      enabled: true
```

Virtual threads giúp quản lý nhiều tác vụ blocking thuận tiện hơn, nhưng không biến JDBC thành non-blocking I/O. Cần hiểu rõ thread model của transport và dependency để chọn cách thực thi.

### Chọn cách thực thi

| Nguồn dữ liệu | Hướng phù hợp |
| --- | --- |
| Reactive repository hoặc WebClient | Trả về Mono/Flux |
| API Java trả CompletionStage | Trả về CompletionStage ở DataFetcher phù hợp |
| Service blocking trên MVC | Có thể trả trực tiếp T; cân nhắc Executor/virtual threads nếu cần |
| Service blocking trên WebFlux | Chuyển công việc sang Executor phù hợp hoặc dùng Callable với configurer |
| Event stream | Trả Flux từ Subscription |

Không nên dùng `CompletableFuture.supplyAsync` với common pool một cách tùy tiện cho các lời gọi blocking. Hãy quản lý Executor, giới hạn concurrency và chính sách timeout rõ ràng.

## 7. AsyncExecutionStrategy và thực thi field đồng thời

GraphQL Java thường sử dụng `AsyncExecutionStrategy` để điều phối việc fetch các field. DataFetcher có thể trả về `CompletionStage`; engine chờ các stage hoàn thành và phối hợp kết quả theo cây GraphQL.

Ví dụ query:

```graphql
query {
  bookById(id: "book-1") {
    title
    inventory
    reviews {
      rating
    }
  }
}
```

Nếu các field inventory và reviews là những nhánh độc lập, GraphQL có thể thực thi các data fetcher tương ứng đồng thời thay vì chờ nhánh này xong mới bắt đầu nhánh kia. Đây là lợi ích của async execution, nhưng không bảo đảm mọi lời gọi database tự động chạy song song hoặc nhanh hơn.

Không được dựa vào thứ tự hoàn tất của các field Query độc lập. Nếu các bước phụ thuộc nhau, biểu diễn dependency trong resolver/service hoặc dùng một use case điều phối rõ ràng.

Đối với Mutation, các top-level mutation fields được thực thi tuần tự theo đặc tả GraphQL. Async return vẫn có thể được dùng trong từng field, nhưng không làm thay đổi quy tắc tuần tự của các root mutation fields.

## 8. Lỗi trong các kiểu return bất đồng bộ

Lỗi có thể phát sinh ở nhiều thời điểm:

| Nguồn lỗi | Ví dụ |
| --- | --- |
| Trước khi trả async handle | Method ném exception ngay khi được gọi |
| Trong CompletionStage | Future hoàn tất exceptionally |
| Trong Mono | Pipeline phát ra error signal |
| Trong Flux của Query | Một phần tử hoặc upstream kết thúc bằng error |
| Trong Flux của Subscription | Publisher phát error sau khi transport đã subscribe |
| Trước khi gọi DataFetcher | GraphQL document parse hoặc validation thất bại |

Ví dụ lỗi từ Mono:

```java
@QueryMapping
public Mono<Book> bookById(@Argument String id) {
    return bookService.findById(id)
            .switchIfEmpty(Mono.error(
                    new BookNotFoundException(id)));
}
```

Ví dụ lỗi từ CompletionStage:

```java
@QueryMapping
public CompletableFuture<Book> bookById(@Argument String id) {
    return bookService.findByIdAsync(id)
            .toCompletableFuture();
}
```

Lỗi trong async handle được GraphQL engine quan sát khi stage hoặc publisher hoàn tất. Với Query/Mutation field thông thường, Spring for GraphQL dùng exception handling tích hợp để chuyển lỗi data fetching thành một entry trong response errors.

## 9. GraphQL response có data và errors

GraphQL cho phép một response chứa cả dữ liệu đã lấy được và lỗi của một field. Ví dụ một field reviews thất bại nhưng title vẫn thành công:

```json
{
  "data": {
    "bookById": {
      "title": "Spring GraphQL",
      "reviews": null
    }
  },
  "errors": [
    {
      "message": "Review service is unavailable",
      "path": ["bookById", "reviews"]
    }
  ]
}
```

Đây là partial response. Field lỗi được đặt null theo quy tắc GraphQL nullability; các field độc lập đã phân giải thành công vẫn có thể xuất hiện trong data.

Nếu field lỗi được khai báo non-null, GraphQL truyền null lên parent gần nhất có thể nhận null. Quá trình đó có thể tiếp tục lên cao hơn trong cây response. Vì vậy, nullability trong SDL ảnh hưởng trực tiếp đến phạm vi dữ liệu bị mất khi một resolver thất bại.

GraphQL error thường có các thông tin:

- message: thông điệp lỗi.
- locations: vị trí field trong GraphQL document nếu xác định được.
- path: đường dẫn đến field gây lỗi.
- extensions: metadata bổ sung như mã lỗi hoặc classification.

Không phải mọi lỗi đều là HTTP 500. Lỗi ở một field có thể được trả trong GraphQL response cùng HTTP response bình thường, tùy transport và loại lỗi. Client cần kiểm tra cả data và errors.

## 10. Xử lý lỗi bằng @GraphQlExceptionHandler

Với annotated controllers, có thể dùng `@GraphQlExceptionHandler` để xử lý exception phát sinh trong quá trình gọi handler method. Method xử lý lỗi đặt trong cùng controller chỉ áp dụng cho controller đó; nếu đặt trong `@ControllerAdvice`, nó có thể áp dụng cho nhiều controller.

Ví dụ domain exception:

```java
public class BookNotFoundException extends RuntimeException {

    public BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}
```

Global exception advice:

```java
@ControllerAdvice
public class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handle(
            GraphqlErrorBuilder<?> errorBuilder,
            BookNotFoundException exception) {

        return errorBuilder
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found")
                .build();
    }
}
```

`GraphqlErrorBuilder` được Spring cung cấp trong method argument và đã gắn với `DataFetchingEnvironment` hiện tại. Điều này giúp tạo error có path và thông tin thực thi đúng field. Trong ví dụ, client nhận thông báo an toàn; chi tiết ID hoặc thông tin nội bộ có thể được ghi log phía server theo chính sách của ứng dụng.

Spring GraphQL cung cấp các nhóm lỗi thường dùng qua `ErrorType`:

| ErrorType | Trường hợp phù hợp |
| --- | --- |
| `BAD_REQUEST` | Input hoặc yêu cầu không hợp lệ |
| `UNAUTHORIZED` | Chưa xác thực |
| `FORBIDDEN` | Không đủ quyền |
| `NOT_FOUND` | Không tìm thấy tài nguyên |
| `INTERNAL_ERROR` | Lỗi hệ thống không dự kiến |

Không nên trả trực tiếp exception message cho mọi loại lỗi. Message có thể chứa SQL, tên bảng, URL nội bộ hoặc thông tin nhạy cảm. Hãy ánh xạ lỗi domain sang message và classification phù hợp với hợp đồng API.

## 11. DataFetcherExceptionResolver cho DataFetcher không dùng controller

`@GraphQlExceptionHandler` tích hợp với annotated controller invocation. Nếu ứng dụng đăng ký DataFetcher thủ công bằng GraphQL Java hoặc dùng một loại DataFetcher khác, có thể dùng `DataFetcherExceptionResolver`.

Spring Boot tự phát hiện các bean kiểu `DataFetcherExceptionResolver` và đưa chúng vào cơ chế xử lý lỗi của `GraphQlSource`. Có thể đăng ký nhiều resolver; chúng được thử theo thứ tự cho tới khi một resolver chuyển exception thành danh sách `GraphQLError`.

`DataFetcherExceptionResolverAdapter` là lớp tiện ích có các method protected để ánh xạ exception thành một hoặc nhiều GraphQL errors. Khi cần xử lý lỗi dùng chung cho DataFetcher cấp thấp, đây là điểm mở rộng phù hợp.

Lưu ý phạm vi:

- Exception từ controller handler: ưu tiên `@GraphQlExceptionHandler`.
- Exception từ DataFetcher tùy biến: dùng `DataFetcherExceptionResolver`.
- Lỗi parse hoặc validation request trước khi DataFetcher chạy: không được xử lý bởi DataFetcherExceptionResolver; cần xem xét transport interceptor.
- Lỗi phát sinh sau khi Subscription publisher đã được subscribe: dùng `SubscriptionExceptionResolver`.

## 12. Lỗi trong Subscription publisher

Subscription có vòng đời khác Query. DataFetcher ban đầu chỉ trả về một Publisher; sau đó transport subscribe vào Publisher và nhận nhiều event. Vì vậy, nếu publisher phát error sau khi subscription đã bắt đầu, lỗi đó xảy ra sau khi DataFetcher ban đầu hoàn tất.

`DataFetcherExceptionResolver` không xử lý được error signal phát ra sau thời điểm này. Spring for GraphQL cung cấp `SubscriptionExceptionResolver` để chuyển lỗi từ Subscription Publisher thành GraphQL errors gửi qua transport, ví dụ thông điệp cuối cùng của WebSocket.

Ví dụ một publisher có thể thất bại:

```java
@SubscriptionMapping
public Flux<Book> bookPublished() {
    return eventService.bookPublished()
            .onErrorMap(
                    EventSourceUnavailableException.class,
                    ex -> new BookEventStreamException());
}
```

Đoạn code chuyển exception nguồn thành domain exception có ý nghĩa. Để định dạng lỗi cuối của subscription, đăng ký `SubscriptionExceptionResolver` phù hợp với phiên bản Spring for GraphQL đang dùng.

Đừng dùng `DataFetcherExceptionResolver` như thể nó xử lý toàn bộ vòng đời publisher. Hãy phân biệt lỗi xảy ra khi tạo publisher với lỗi xảy ra sau khi publisher đã phát event.

## 13. Request errors khác data fetching errors

Không phải mọi GraphQL error đều xuất phát từ resolver:

| Giai đoạn | Ví dụ | Cơ chế xử lý |
| --- | --- | --- |
| Parse document | Cú pháp GraphQL sai | GraphQL engine và transport |
| Validate document | Field hoặc argument không tồn tại | GraphQL engine và transport |
| Input coercion | Variable sai kiểu hoặc thiếu non-null value | GraphQL engine |
| Data fetching | Resolver ném exception hoặc async stage thất bại | `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver` |
| Subscription stream | Publisher phát error sau khi subscribe | `SubscriptionExceptionResolver` |

Lỗi parse/validation xuất hiện trước khi DataFetcher được gọi. Response thường có `data: null` và errors không có field path. Nếu cần tùy biến các lỗi request-level, có thể kiểm tra `ExecutionResult` trong `WebGraphQlInterceptor`.

## 14. Timeout và cancellation

Một GraphQL request có thể mất quá nhiều thời gian do truy vấn chậm, dịch vụ phụ thuộc bị treo hoặc stream không kết thúc. Spring for GraphQL cung cấp `TimeoutWebGraphQlInterceptor` cho web transports:

```java
@Configuration
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(Duration.ofSeconds(5));
    }
}
```

Khi request vượt timeout, interceptor kết thúc request theo chính sách transport và gửi tín hiệu cancel lên pipeline. Reactive data fetchers có thể nhận cancellation để dừng công việc đang thực hiện.

Timeout không thay thế timeout ở từng dependency. Ứng dụng nên cân nhắc:

- Timeout của database query.
- Timeout của WebClient hoặc HTTP client.
- Timeout của GraphQL request.
- Giới hạn concurrency và số phần tử stream.
- Cancellation propagation đến các nguồn dữ liệu.

Nếu chỉ đặt timeout ở tầng ngoài nhưng dependency không hỗ trợ cancellation hoặc tiếp tục chạy ở background, tài nguyên server vẫn có thể bị tiêu thụ sau khi client đã ngắt kết nối.

## 15. Context propagation khi chuyển thread

Async execution có thể khiến resolver và các thành phần liên quan chạy trên thread khác với thread tiếp nhận request. Spring for GraphQL hỗ trợ truyền context từ transport qua GraphQL Java:

- Với Spring MVC, có thể propagate các giá trị `ThreadLocal` thông qua cơ chế Micrometer Context Propagation khi đã đăng ký accessor phù hợp.
- Với Spring WebFlux, reactive data fetcher có thể đọc Reactor `Context` được truyền từ request pipeline, bao gồm context do `WebGraphQlInterceptor` thêm vào.

Trong reactive pipeline, nên dùng Reactor Context hoặc GraphQLContext để truyền request-scoped data thay vì tự lưu trạng thái vào mutable instance field. Nếu tự chuyển sang thread khác, hãy hiểu rõ context nào được propagate và context nào cần đăng ký riêng.

Không giả định mọi ThreadLocal tự động có mặt trên mọi thread. Nếu ứng dụng dùng MDC, request attributes hoặc security context tùy biến trong tác vụ bất đồng bộ, cần xác minh propagation theo cấu hình hiện tại.

## 16. DataFetcherResult khi cần metadata

Thông thường resolver chỉ trả dữ liệu domain. Khi cần gắn thêm GraphQL errors, extensions hoặc local context vào kết quả, có thể trả `DataFetcherResult<P>`.

Ví dụ:

```java
@QueryMapping
public DataFetcherResult<Book> bookById(@Argument String id) {
    Book book = bookService.findById(id);

    return DataFetcherResult.<Book>newResult()
            .data(book)
            .localContext(Map.of("source", "catalog"))
            .build();
}
```

`DataFetcherResult` là kiểu return đầy đủ của GraphQL Java. Generic `P` có thể là giá trị thường hoặc một kiểu async được hỗ trợ, chẳng hạn Mono. Chỉ dùng khi thực sự cần metadata hoặc local context; với resolver thông thường, trả trực tiếp `T`, `Mono<T>` hoặc `Flux<T>` đơn giản hơn.

## 17. Kiểm thử async return và error

Có thể dùng `@GraphQlTest` và `GraphQlTester` để kiểm tra resolver trả Mono:

```java
@GraphQlTest(BookQueryController.class)
class BookAsyncQueryTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    ReactiveBookService bookService;

    @Test
    void returnsBookFromMono() {
        given(bookService.findById("book-1"))
                .willReturn(Mono.just(
                        new Book("book-1", "Spring GraphQL")));

        graphQlTester.document("""
                query {
                    bookById(id: "book-1") {
                        id
                        title
                    }
                }
                """)
                .execute()
                .path("bookById.title")
                .entity(String.class)
                .isEqualTo("Spring GraphQL");
    }
}
```

Kiểm thử lỗi:

```java
given(bookService.findById("missing"))
        .willReturn(Mono.error(
                new BookNotFoundException("missing")));
```

Sau đó thực thi query và xác nhận GraphQL response có field path cùng error classification mà advice đã cấu hình. Cũng cần kiểm tra data theo nullability của schema.

Với reactive service, dùng Reactor Test và `StepVerifier` để kiểm tra pipeline độc lập. `GraphQlTester` kiểm tra tích hợp từ GraphQL document qua resolver đến response; hai cấp test phục vụ mục đích khác nhau.

Các tình huống nên kiểm thử:

- Mono phát ra giá trị.
- Mono empty cho field nullable và non-null.
- Mono phát error.
- Flux Query được tổng hợp thành danh sách.
- Flux Query phát error giữa stream.
- Subscription publisher phát nhiều event và sau đó phát error.
- Timeout/cancellation.
- Context vẫn có mặt sau khi chuyển thread hoặc qua reactive pipeline.

## 18. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Resolver vẫn chặn event-loop | Gọi API blocking hoặc dùng `block()` trong WebFlux | Dùng reactive client hoặc chuyển blocking call sang Executor phù hợp |
| Mono empty tạo lỗi non-null | SDL khai báo field non-null nhưng resolver không có giá trị | Điều chỉnh nullability hoặc bảo đảm domain luôn trả giá trị |
| Flux Query chỉ trả sau khi hoàn tất | Flux của field thường được gom thành List | Dùng pagination cho danh sách lớn; dùng Subscription nếu cần event stream |
| Subscription không gửi event | Transport không hỗ trợ streaming hoặc publisher không phát dữ liệu | Kiểm tra WebSocket/RSocket, subscription mapping và nguồn event |
| Lỗi async không được đổi thành mã nghiệp vụ | Chưa đăng ký exception resolver phù hợp | Dùng `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver` |
| Lỗi Subscription không qua resolver thông thường | Error phát ra sau khi publisher đã được subscribe | Đăng ký `SubscriptionExceptionResolver` |
| Parse error không vào DataFetcherExceptionResolver | Request chưa đến giai đoạn data fetching | Xử lý ở transport/interceptor nếu cần tùy biến |
| Response mất cả parent object | Field lỗi nằm dưới nhánh non-null | Xem lại nullability và vị trí cho phép null trong SDL |
| Timeout nhưng công việc vẫn chạy | Dependency không hỗ trợ cancellation hoặc code đã tách khỏi reactive chain | Cấu hình timeout ở dependency và propagate cancellation |
| Request context biến mất sau đổi thread | ThreadLocal không được propagate hoặc Reactor Context không được giữ | Dùng context propagation phù hợp và kiểm thử ở thread boundary |
| CompletableFuture dùng common pool quá tải | Blocking task chiếm worker threads của common pool | Dùng Executor riêng có giới hạn và quản lý lifecycle |

Khi debug, hãy xác định lỗi xuất hiện trước hay sau khi DataFetcher được gọi. Sau đó xác định resolver trả về kiểu gì và lỗi được phát ra đồng bộ, qua CompletionStage, qua Reactor signal hay sau khi Subscription đã bắt đầu.

## 19. Nguyên tắc thiết kế async return và error

- Dùng `Mono<T>` cho kết quả bất đồng bộ có tối đa một giá trị.
- Dùng `Flux<T>` cho nhiều giá trị; nhớ rằng Flux của Query thường được gom thành List.
- Dùng `Flux<T>` trong Subscription khi cần phát event liên tục.
- Dùng `CompletionStage<T>` khi tích hợp API Java bất đồng bộ ở tầng DataFetcher.
- Dùng `Callable<T>` cho công việc blocking cần Executor được cấu hình.
- Không gọi `block()` trong reactive request pipeline.
- Không dùng common pool cho blocking work mà không đánh giá tải.
- Thiết kế nullability để lỗi một field không làm mất nhiều dữ liệu hơn mức cần thiết.
- Dùng `@GraphQlExceptionHandler` cho exception từ annotated controller.
- Dùng `DataFetcherExceptionResolver` cho DataFetcher khác.
- Dùng `SubscriptionExceptionResolver` cho lỗi từ Subscription publisher.
- Dùng `WebGraphQlInterceptor` cho request-level errors nếu cần tùy biến.
- Không trả stack trace hoặc thông tin hạ tầng cho client.
- Cấu hình timeout và cancellation ở cả GraphQL request lẫn dependency.
- Kiểm thử partial response, error path, null propagation và context propagation.

## 20. Bài tập thực hành

Xây dựng API thư viện có Query và Subscription bất đồng bộ:

1. Tạo `ReactiveBookService` trả `Mono<Book>` cho `findById`.
2. Viết `@QueryMapping` trả `Mono<Book>` và kiểm tra kết quả bằng `GraphQlTester`.
3. Tạo method trả `Flux<Book>` cho field danh sách và xác nhận response Query là một list đã được tổng hợp.
4. Tạo `BookEventService` phát `Flux<Book>` và ánh xạ thành `@SubscriptionMapping`.
5. Tạo `BookNotFoundException` và xử lý bằng `@GraphQlExceptionHandler` với `ErrorType.NOT_FOUND`.
6. Thêm một DataFetcher thủ công và xử lý lỗi của nó qua `DataFetcherExceptionResolver`.
7. Làm publisher Subscription phát lỗi sau một vài event và cấu hình `SubscriptionExceptionResolver`.
8. Thêm `TimeoutWebGraphQlInterceptor` và kiểm tra cancellation khi request vượt thời gian.
9. Tạo một field nullable và một field non-null, sau đó quan sát khác biệt về null propagation khi resolver phát error.
10. Giải thích vì sao lỗi parse request không được xử lý bởi DataFetcherExceptionResolver.

Sau bài tập, hãy phân biệt được async return với streaming Subscription, biết chọn Mono/Flux/CompletionStage/Callable, và chọn đúng exception resolver theo giai đoạn lỗi.

## 21. Tài liệu tham khảo

- [Spring for GraphQL — Request Execution, Thread Model, Reactive DataFetcher and Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers, Return Values and Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring Framework — WebFlux Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)

Chi tiết kiểu return được hỗ trợ, virtual thread integration và exception resolver có thể thay đổi theo phiên bản Spring Boot, Spring for GraphQL và GraphQL Java. Khi nâng cấp dependency, hãy kiểm tra reference documentation đúng phiên bản dự án đang sử dụng.
