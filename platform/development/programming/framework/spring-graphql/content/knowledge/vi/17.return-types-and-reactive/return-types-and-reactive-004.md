# CompletableFuture

Trong Spring for GraphQL, một resolver không nhất thiết phải trả dữ liệu ngay tại thời điểm được gọi. Phương thức annotated controller có thể trả về `CompletableFuture<T>` để biểu diễn một kết quả sẽ hoàn tất trong tương lai. GraphQL Java nhận biết kết quả bất đồng bộ này, chờ future hoàn tất trong quá trình thực thi operation rồi tiếp tục hoàn thiện response.

`CompletableFuture` phù hợp khi ứng dụng gọi dịch vụ từ xa, database client bất đồng bộ hoặc cần kết hợp nhiều tác vụ độc lập. Nó giúp resolver không phải chặn luồng hiện tại để chờ kết quả. Tuy nhiên, tạo một future bằng `supplyAsync` rồi chạy một lời gọi blocking trên thread pool vẫn là công việc blocking; muốn đạt lợi ích non-blocking thực sự, nguồn dữ liệu nên cung cấp API bất đồng bộ hoặc reactive.

## 1. CompletableFuture là gì?

`CompletableFuture<T>` là một implementation của `Future<T>` và `CompletionStage<T>` trong Java. Nó đại diện cho một kết quả kiểu `T` có thể hoàn tất sau này, hoàn tất bình thường với giá trị hoặc hoàn tất bất thường bằng exception.

Ví dụ:

```java
CompletableFuture<Book> future = bookClient.findById("book-01");
```

Lời gọi trên trả về ngay một future. Khi client từ xa nhận được dữ liệu, future hoàn tất với một `Book`; nếu request thất bại, future hoàn tất bất thường.

Các trạng thái thường gặp:

| Trạng thái | Ý nghĩa |
| --- | --- |
| Incomplete | Tác vụ chưa hoàn tất |
| Completed normally | Có kết quả kiểu `T` |
| Completed exceptionally | Tác vụ kết thúc bằng exception |
| Cancelled | Future bị hủy theo cơ chế hỗ trợ của tác vụ |

`CompletableFuture` không đồng nghĩa với một thread. Một future có thể đại diện cho I/O bất đồng bộ do HTTP client hoặc driver database quản lý mà không chiếm thread để chờ. Khi dùng `supplyAsync`, Java mới lên lịch một tác vụ trên executor để chạy supplier.

## 2. Trả CompletableFuture từ @QueryMapping

Giả sử GraphQL schema khai báo:

```graphql
type Query {
    bookById(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

Service dùng một HTTP client bất đồng bộ và trả future:

```java
@Service
public class BookService {

    private final BookClient bookClient;

    public BookService(BookClient bookClient) {
        this.bookClient = bookClient;
    }

    public CompletableFuture<Book> findByIdAsync(String id) {
        return bookClient.findById(id);
    }
}
```

Controller trả trực tiếp future cho Spring for GraphQL:

```java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public CompletableFuture<Book> bookById(@Argument("id") String id) {
        return bookService.findByIdAsync(id);
    }
}
```

Spring đăng ký phương thức controller làm data fetcher. GraphQL Java nhận `CompletableFuture<Book>` như một kết quả bất đồng bộ. Khi future hoàn tất, giá trị `Book` được dùng để phân giải các field con như `id` và `title`.

Có thể dùng cùng cách với `@SchemaMapping`:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(Book book) {
    return authorService.findByIdAsync(book.authorId());
}
```

Field `Book.author` chỉ hoàn tất khi future trả về `Author`. Nếu field không được chọn trong selection set, resolver không cần được gọi.

## 3. Tạo CompletableFuture từ tác vụ blocking

Nếu thư viện hiện tại chỉ có API đồng bộ, có thể cô lập lời gọi blocking bằng `CompletableFuture.supplyAsync` và một executor riêng:

```java
@Service
public class BookService {

    private final BookRepository bookRepository;
    private final Executor graphqlExecutor;

    public BookService(
            BookRepository bookRepository,
            @Qualifier("graphqlExecutor") Executor graphqlExecutor) {
        this.bookRepository = bookRepository;
        this.graphqlExecutor = graphqlExecutor;
    }

    public CompletableFuture<Book> findByIdAsync(String id) {
        return CompletableFuture.supplyAsync(
            () -> bookRepository.findById(id).orElse(null),
            graphqlExecutor
        );
    }
}
```

Có thể khai báo executor trong Spring:

```java
@Configuration
public class GraphQlAsyncConfiguration {

    @Bean("graphqlExecutor")
    public ThreadPoolTaskExecutor graphqlExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("graphql-io-");
        return executor;
    }
}
```

Các con số trên chỉ là ví dụ khởi đầu, không phải cấu hình tối ưu cho mọi ứng dụng. Cần chọn pool size và queue capacity theo latency của dependency, số request đồng thời, giới hạn kết nối database và khả năng chịu tải của dịch vụ bên ngoài. Theo dõi queue depth, active thread, rejected task và thời gian chờ để điều chỉnh.

Không nên mặc định dùng `ForkJoinPool.commonPool()` cho mọi tác vụ I/O blocking. Common pool có thể được chia sẻ với các tác vụ khác của JVM; một nhóm lời gọi blocking kéo dài có thể làm cạn thread và gây chậm ở các phần không liên quan. Dùng executor có giới hạn và mục đích rõ ràng cho công việc blocking.

Nếu HTTP client hoặc database driver đã trả `CompletableFuture`, hãy trả future đó trực tiếp. Không cần bọc một API async vào `supplyAsync` chỉ để tạo thêm một lớp scheduling.

## 4. Kết hợp nhiều bước bất đồng bộ

`CompletableFuture` cung cấp các phép nối để xây dựng pipeline. Hai phương thức thường dùng là `thenApply` và `thenCompose`:

- `thenApply` biến đổi giá trị đã hoàn tất bằng một hàm đồng bộ và trả về future chứa giá trị mới.
- `thenCompose` gọi một hàm trả về future khác rồi làm phẳng kết quả, tránh tạo `CompletableFuture<CompletableFuture<T>>`.

Ví dụ, lấy sách rồi tải tác giả:

```java
public CompletableFuture<BookDetails> findDetails(String bookId) {
    return bookClient.findById(bookId)
        .thenCompose(book -> authorClient.findById(book.authorId())
            .thenApply(author -> new BookDetails(book, author)));
}
```

`bookClient.findById` trả về `CompletableFuture<Book>`. Sau khi có sách, `thenCompose` gọi `authorClient.findById`, rồi `thenApply` tạo `BookDetails` từ hai kết quả. Nếu bất kỳ future nào hoàn tất bất thường, pipeline cũng hoàn tất bất thường trừ khi lỗi được xử lý rõ ràng.

Khi hai nguồn dữ liệu độc lập, có thể khởi chạy cả hai rồi kết hợp bằng `thenCombine`:

```java
public CompletableFuture<Dashboard> loadDashboard(String customerId) {
    CompletableFuture<Customer> customerFuture =
        customerClient.findById(customerId);
    CompletableFuture<List<Order>> ordersFuture =
        orderClient.findRecentByCustomer(customerId);

    return customerFuture.thenCombine(
        ordersFuture,
        Dashboard::new
    );
}
```

Hai request được khởi chạy trước khi kết hợp. Future kết quả hoàn tất khi cả hai kết quả cần thiết đều sẵn sàng. Nếu một future lỗi, future kết hợp cũng lỗi.

### Khi nào dùng thenApply, thenCompose và thenCombine?

| Phương thức | Trường hợp dùng | Kiểu kết quả |
| --- | --- | --- |
| `thenApply` | Chuyển đổi một giá trị đã có | `CompletableFuture<U>` |
| `thenCompose` | Bước tiếp theo tự trả về một future | `CompletableFuture<U>` đã được làm phẳng |
| `thenCombine` | Kết hợp hai future độc lập | `CompletableFuture<R>` |
| `allOf` | Chờ nhiều future hoàn tất mà không cần kết hợp giá trị trực tiếp | `CompletableFuture<Void>` |

`allOf` hữu ích khi cần chờ một nhóm tác vụ rồi đọc kết quả từ từng future. Nó không tự thu thập các giá trị thành list; ứng dụng cần gọi `join()` trên từng future sau khi `allOf` hoàn tất, hoặc dùng một hàm kết hợp riêng.

## 5. Async callback và lựa chọn executor

Các phương thức không có hậu tố `Async`, như `thenApply`, có thể chạy callback trên thread hoàn tất future trước đó hoặc thread gọi callback nếu future đã hoàn tất. Các biến thể `thenApplyAsync`, `thenComposeAsync` và `thenCombineAsync` lên lịch callback bất đồng bộ, thường trên common pool nếu không truyền executor.

Ví dụ chỉ định executor:

```java
return bookClient.findById(bookId)
    .thenApplyAsync(this::toBookView, graphqlExecutor);
```

Chọn executor tường minh khi callback thực hiện công việc tốn CPU hoặc blocking. Với callback rất nhỏ chỉ chuyển đổi một object, biến thể không `Async` thường đủ và tránh scheduling thừa. Tránh gọi `join()` hoặc `get()` bên trong callback để chờ một future khác; cách đó có thể chiếm thread, gây deadlock hoặc làm mất lợi ích bất đồng bộ. Dùng `thenCompose` để nối pipeline.

## 6. Nhiều field GraphQL và thực thi bất đồng bộ

GraphQL Java có thể thực thi các root field của query độc lập. Nếu resolver trả future, engine có thể theo dõi các future đó và hoàn tất response khi những field được yêu cầu đã có kết quả. Ví dụ một operation yêu cầu sách, tác giả và danh sách mới nhất; mỗi resolver có thể gọi một service bất đồng bộ riêng.

Điều này không có nghĩa mọi method Java đều tự chạy trên thread riêng. Một resolver trả object đồng bộ vẫn thực thi theo cách đồng bộ của data fetcher. Một resolver trả future đã có sẵn từ HTTP client có thể không cần chiếm thread chờ I/O. Một resolver dùng `supplyAsync` chiếm một thread trong executor khi supplier đang chạy.

Không dựa vào thứ tự hoàn tất của các root query field. Nếu một thao tác cần thực hiện sau thao tác khác, hãy biểu diễn dependency trong cùng pipeline bằng `thenCompose`, hoặc mô hình hóa thao tác thay đổi dữ liệu bằng mutation. Root fields của mutation được GraphQL thực thi tuần tự; query không có bảo đảm thứ tự đó.

## 7. Xử lý exception trong CompletableFuture

Future có thể hoàn tất bất thường khi service ném exception hoặc lời gọi từ xa thất bại. GraphQL Java chuyển lỗi của data fetcher thành lỗi thực thi GraphQL. Spring for GraphQL cung cấp `DataFetcherExceptionResolver` để ánh xạ exception thành lỗi an toàn và phù hợp với API.

Có ba callback phổ biến:

| Phương thức | Công dụng |
| --- | --- |
| `whenComplete` | Quan sát kết quả hoặc lỗi, thường dùng log/metrics; không biến đổi kết quả |
| `exceptionally` | Chuyển lỗi thành một giá trị fallback nếu fallback hợp lệ |
| `handle` | Xử lý cả kết quả và lỗi, có thể tạo ra giá trị thay thế |

Ví dụ ghi log mà vẫn giữ nguyên kết quả thành công hoặc thất bại:

```java
return bookClient.findById(id)
    .whenComplete((book, error) -> {
        if (error != null) {
            logger.warn("Could not load book {}", id, error);
        }
    });
```

Ví dụ dùng fallback chỉ khi nghiệp vụ cho phép:

```java
return recommendationClient.findForBook(id)
    .exceptionally(error -> List.of());
```

Nếu danh sách gợi ý có thể được xem như rỗng khi dịch vụ gợi ý tạm thời lỗi, fallback này có thể phù hợp. Không nên dùng `exceptionally(error -> null)` một cách tùy tiện: nó biến lỗi thành dữ liệu null và có thể che mất sự cố hoặc kích hoạt null propagation nếu field là non-null.

Exception phát sinh trong pipeline thường được bọc bởi `CompletionException` hoặc `ExecutionException`. Khi ánh xạ lỗi, cần xem cause để nhận diện exception nghiệp vụ. Không trả stack trace hoặc thông tin hệ thống nội bộ cho client.

Nếu cần chuyển exception thành GraphQL error có mã, có thể triển khai `DataFetcherExceptionResolver` hoặc `DataFetcherExceptionResolverAdapter`. Resolver nên nhận diện loại lỗi nghiệp vụ, tạo thông điệp phù hợp và bổ sung error code trong `extensions`; lỗi không được nhận diện có thể để resolver khác hoặc cơ chế mặc định xử lý.

## 8. Timeout và fallback

Java cung cấp `orTimeout` và `completeOnTimeout` để đặt giới hạn thời gian cho future:

```java
return bookClient.findById(id)
    .orTimeout(2, TimeUnit.SECONDS);
```

`orTimeout` hoàn tất future bất thường bằng `TimeoutException` nếu thời hạn vượt quá. Có thể dùng `completeOnTimeout` khi một giá trị dự phòng có ý nghĩa:

```java
return recommendationClient.findForBook(id)
    .completeOnTimeout(List.of(), 1, TimeUnit.SECONDS);
```

Timeout của future không đảm bảo lời gọi I/O gốc đã bị hủy. Nếu HTTP client, database driver hoặc tác vụ nền vẫn đang chạy, nó có thể tiếp tục sử dụng tài nguyên. Cần cấu hình timeout/cancellation ở chính client hoặc dependency khi có hỗ trợ. Cũng cần tránh đặt timeout lên một future được chia sẻ cho nhiều consumer nếu việc hoàn tất timeout có thể ảnh hưởng đến tất cả consumer đó.

Chọn timeout theo SLA và thời gian thực tế của dependency. Không dùng một con số tùy tiện cho mọi service. Khi timeout, hãy phân biệt thao tác đọc có thể thử lại với command có side effect cần idempotency.

## 9. Cancellation và request lifecycle

`CompletableFuture` có phương thức `cancel`, nhưng việc hủy future không tự động bảo đảm mọi công việc bên dưới dừng lại. Một HTTP request đã gửi, một JDBC query hoặc một tác vụ đang chạy có thể tiếp tục nếu client/driver không hỗ trợ cancellation.

Không nên giả định client GraphQL đóng kết nối thì mọi future trong operation chắc chắn dừng ngay. Cần kiểm tra hành vi cancellation của transport, GraphQL Java và data source đang dùng. Với tác vụ tốn tài nguyên, thiết kế deadline, timeout và cancellation propagation rõ ràng; bảo đảm thao tác cleanup không làm lộ hoặc ghi dữ liệu dở dang.

Đối với mutation, hủy request sau khi side effect đã commit không có nghĩa side effect được rollback. Client có thể không nhận được response và phải retry bằng cùng idempotency key để lấy lại kết quả đã ghi nhận.

## 10. Context, bảo mật và transaction khi đổi thread

Một điểm dễ bị bỏ qua là `CompletableFuture` có thể chạy callback trên thread khác. Nhiều context của Spring hoặc ứng dụng được lưu bằng `ThreadLocal`, chẳng hạn security context, MDC logging, locale hoặc transaction context. Không nên giả định các context này tự động đi theo future khi tác vụ chuyển thread.

Với dữ liệu request cần dùng trong tác vụ async, nên truyền tường minh các giá trị cần thiết, ví dụ tenant ID, user ID đã xác thực hoặc correlation ID. Nếu cần truyền `SecurityContext` hoặc MDC qua executor, cấu hình cơ chế context propagation phù hợp như `TaskDecorator` hoặc executor được bọc theo cơ chế của Spring Security.

Transaction JDBC/JPA thông thường gắn với thread. Nếu mở transaction ở thread xử lý GraphQL rồi chuyển việc truy vấn sang `supplyAsync` trên thread khác, transaction và persistence context không tự động được chia sẻ. Không truyền entity đang được quản lý hoặc `EntityManager` qua thread tùy tiện.

Nếu tác vụ async cần transaction, hãy để một service method được gọi trên worker thread tự mở transaction qua Spring proxy, hoặc dùng mô hình transaction phù hợp với công nghệ dữ liệu đang sử dụng. Một method `@Transactional` trả về `CompletableFuture` không mặc nhiên giữ transaction mở cho đến khi future hoàn tất trên thread khác; ranh giới transaction phải được thiết kế và kiểm thử rõ ràng.

## 11. CompletableFuture trong @BatchMapping và DataLoader

Các resolver batch cũng có thể trả về kết quả bất đồng bộ. Ví dụ `@BatchMapping` có thể trả về `CompletableFuture<Map<Book, Author>>` nếu việc tải nhóm tác giả diễn ra bất đồng bộ:

```java
@Controller
public class BookAuthorController {

    private final AuthorService authorService;

    public BookAuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public CompletableFuture<Map<Book, Author>> authors(List<Book> books) {
        Set<String> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

        return authorService.findAllByIdsAsync(authorIds)
            .thenApply(authorsById -> {
                Map<Book, Author> result = new HashMap<>();
                for (Book book : books) {
                    result.put(book, authorsById.get(book.authorId()));
                }
                return result;
            });
    }
}
```

Spring for GraphQL kết hợp `@BatchMapping` với DataLoader để gom các source object. Future ở đây đại diện cho kết quả của cả batch. Cần trả về ánh xạ đầy đủ theo source object và xử lý trường hợp không tìm thấy dữ liệu theo nullability của field.

Nếu dùng DataLoader trực tiếp, `load(key)` thường trả về một future cho key đó. Resolver có thể trả future này cho GraphQL Java thay vì chặn bằng `join()`:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataFetchingEnvironment environment) {
    DataLoader<String, Author> loader =
        environment.getDataLoader("authorLoader");
    return loader.load(book.authorId());
}
```

Loader phải được đăng ký đúng tên và quản lý theo request, thường qua `BatchLoaderRegistry` trong Spring for GraphQL. Không tự tạo một DataLoader dùng chung toàn ứng dụng nếu cache có thể làm dữ liệu của request hoặc người dùng này lộ sang request khác.

## 12. CompletableFuture khác Mono và Flux như thế nào?

`CompletableFuture<T>` biểu diễn một kết quả đơn hoàn tất một lần. Reactor `Mono<T>` cũng biểu diễn tối đa một kết quả, còn `Flux<T>` biểu diễn một luồng có thể phát ra nhiều phần tử theo thời gian.

| Kiểu | Mô hình | Thường dùng cho |
| --- | --- | --- |
| `CompletableFuture<T>` | Một kết quả bất đồng bộ | HTTP call trả một object, tác vụ nền hoàn tất một lần |
| `Mono<T>` | 0 hoặc 1 kết quả reactive | Service reactive trả một object hoặc không có dữ liệu |
| `Flux<T>` | 0 đến nhiều phần tử reactive | Danh sách/luồng dữ liệu, subscription event stream |

Một subscription GraphQL thường cần publisher/`Flux` vì nó phát ra nhiều event trong thời gian tồn tại của subscription. `CompletableFuture` chỉ đại diện cho một kết quả nên không thay thế publisher cho một luồng sự kiện liên tục.

Chọn kiểu trả về phù hợp với stack ứng dụng. Không cần chuyển mọi API sang `CompletableFuture` nếu service đã dùng Reactor xuyên suốt; Spring for GraphQL hỗ trợ các kiểu reactive. Tránh chuyển qua lại giữa future và reactive một cách không cần thiết vì có thể làm phức tạp cancellation, context và error handling.

## 13. Kiểm thử resolver trả CompletableFuture

`GraphQlTester` có thể kiểm thử resolver bất đồng bộ như resolver đồng bộ. Khi gọi `execute()`, tester chờ operation hoàn tất theo cơ chế của tester rồi cho phép kiểm tra path trong response.

Ví dụ:

```java
graphQlTester.document("""
        query($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-01")
    .execute()
    .path("bookById.title")
    .entity(String.class)
    .isEqualTo("Spring in Action");
```

Nên kiểm thử thêm các tình huống:

- Future hoàn tất bình thường với object hợp lệ.
- Future hoàn tất bình thường với `null` cho field nullable.
- Future hoàn tất bất thường và exception được ánh xạ thành GraphQL error phù hợp.
- Future timeout và response chứa lỗi đúng contract.
- Nhiều root field hoàn tất theo thứ tự khác nhau nhưng response vẫn đúng.
- `thenCompose` xử lý dependency giữa các tác vụ mà không gọi `join()`.
- Context/security cần thiết vẫn có mặt trong callback chạy trên executor khác.
- Batch future trả đúng kết quả cho từng source object.

Để kiểm thử pipeline một cách xác định, có thể dùng một `CompletableFuture` do test điều khiển: mock service trả future chưa hoàn tất, sau đó hoàn tất future bằng kết quả hoặc exception. Cách này giúp xác nhận resolver không cần block để lấy dữ liệu và response chỉ hoàn tất sau khi future được resolve.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Resolver vẫn block | Gọi `join()` hoặc `get()` ngay trong controller | Trả future trực tiếp và nối pipeline bằng `thenApply`/`thenCompose` |
| Thread pool cạn | Chạy nhiều tác vụ blocking trên common pool hoặc pool không giới hạn | Dùng executor có giới hạn, theo dõi queue và thời gian xử lý |
| Future lồng nhau | Dùng `thenApply` cho hàm trả future | Dùng `thenCompose` để làm phẳng |
| Lỗi bị biến thành null | Dùng `exceptionally(error -> null)` không có chủ đích | Để lỗi truyền đến GraphQL hoặc chỉ dùng fallback hợp lệ |
| Không thấy SecurityContext trong callback | Callback chạy trên thread khác | Truyền context tường minh hoặc cấu hình context propagation |
| Transaction không bao trùm tác vụ async | Transaction thread-bound kết thúc trước khi future hoàn tất | Mở transaction trong service chạy trên worker thread hoặc dùng mô hình phù hợp |
| Timeout nhưng dependency vẫn chạy | Timeout future không hủy chắc chắn I/O gốc | Cấu hình timeout/cancellation tại HTTP client hoặc driver |
| Subscription chỉ phát một kết quả | Dùng `CompletableFuture` thay cho publisher | Dùng `Flux`/`Publisher` cho stream event |
| Batch resolver trả thiếu dữ liệu | Map không khớp source object hoặc key | Xây dựng mapping đầy đủ và kiểm tra trường hợp không tìm thấy |

## 15. Nguyên tắc sử dụng CompletableFuture

Trả trực tiếp future từ service khi dependency đã hỗ trợ async. Chỉ dùng `supplyAsync` để cô lập công việc blocking khi chưa có API non-blocking, và luôn chọn executor có giới hạn phù hợp. Dùng `thenApply` cho biến đổi đồng bộ, `thenCompose` cho bước async phụ thuộc và `thenCombine` cho các tác vụ độc lập.

Để exception truyền đến cơ chế GraphQL error handling nếu không có fallback hợp lệ. Đặt timeout ở cả future và dependency khi cần, đồng thời hiểu rõ cancellation không tự dừng mọi I/O. Khi đổi thread, truyền context cần thiết một cách tường minh và thiết kế transaction trên đúng thread thực thi.

Trong Spring for GraphQL, `CompletableFuture` là một kiểu return value để resolver cung cấp kết quả bất đồng bộ cho GraphQL Java. Nó không thay thế schema, resolver hay DataLoader; nó giúp biểu diễn thời điểm dữ liệu sẵn sàng. Dùng đúng cách sẽ giảm thời gian chờ blocking, cho phép kết hợp các dependency độc lập và giữ logic controller gọn, trong khi vẫn cần quản lý executor, lỗi, timeout và context cẩn thận.
