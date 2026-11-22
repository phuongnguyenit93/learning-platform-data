# Blocking method trong Spring for GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt method đồng bộ với thao tác blocking I/O.
- Hiểu thread thực thi resolver phải chờ như thế nào khi method gọi tài nguyên bên ngoài.
- Viết `@QueryMapping` và `@SchemaMapping` trả về giá trị Java thông thường.
- Nhận biết khác biệt vận hành giữa Spring MVC và Spring WebFlux.
- Đánh giá rủi ro khi gọi JPA/JDBC, HTTP client đồng bộ hoặc filesystem trong resolver.
- Chọn giữa giá trị đồng bộ, `CompletableFuture` và reactive return type.
- Offload công việc blocking khỏi event-loop khi dùng WebFlux.
- Thiết lập timeout, giới hạn concurrency và theo dõi thread pool.
- Nhận biết tác động của chuyển thread tới transaction, security context và tracing.
- Kiểm thử và quan sát hiệu năng của blocking resolver.

## 1. Blocking method là gì?

Một annotated controller method có thể trả về giá trị Java thông thường:

~~~java
@Controller
class BookQueryController {

    private final BookService bookService;

    BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") UUID id) {
        return bookService.findById(id);
    }
}
~~~

Method `book` được gọi đồng bộ. GraphQL gọi method, chờ method trả về `Book`, sau đó dùng giá trị đó để tiếp tục xử lý selection set.

Bản thân việc method trả về một object đồng bộ chưa có nghĩa nó luôn thực hiện blocking I/O. Nếu method chỉ tính toán trong bộ nhớ hoặc đọc property đã có, nó có thể hoàn tất rất nhanh. Method trở thành blocking theo nghĩa vận hành khi nó phải chờ một thao tác chưa hoàn tất, chẳng hạn:

- Truy vấn database qua JDBC hoặc JPA.
- Gọi HTTP bằng client đồng bộ.
- Đọc file hoặc truy cập filesystem.
- Chờ lock, semaphore hoặc tài nguyên dùng chung.
- Gọi thư viện bên thứ ba có API đồng bộ và chờ kết quả.

Ví dụ:

~~~java
@QueryMapping
public Book book(@Argument("id") UUID id) {
    // findById có thể chờ database trả kết quả.
    return bookRepository.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

Trong thời gian repository chờ database, thread đang chạy resolver không thể dùng để thực hiện công việc khác. Đây là đặc điểm quan trọng cần cân nhắc khi chọn blocking method.

## 2. Vòng đời của một blocking resolver

GraphQL thực thi operation theo selection set. Với một field đồng bộ, resolver được gọi và GraphQL cần nhận kết quả của field đó trước khi hoàn thành các bước phụ thuộc vào kết quả.

Có thể hình dung luồng cơ bản:

~~~mermaid
flowchart TD
    A["HTTP request /graphql"] --> B["Spring GraphQL transport"]
    B --> C["GraphQL execution"]
    C --> D["Invoke synchronous resolver"]
    D --> E["Blocking call: JDBC / JPA / HTTP"]
    E --> F["Thread waits for result"]
    F --> G["Resolver returns Java value"]
    G --> H["Resolve selected fields and build response"]
    H --> I["HTTP response"]
~~~

Ví dụ operation:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
    }
}
~~~

Nếu `Query.book` gọi JPA repository đồng bộ, resolver chỉ trả về sau khi thao tác database hoàn tất. GraphQL sau đó tiếp tục lấy `id` và `title` từ object `Book`.

Với nested field, cùng nguyên tắc áp dụng cho từng resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorRepository.findById(book.getAuthorId())
            .orElse(null);
}
~~~

Nếu query lấy nhiều sách và mỗi lần resolve `Book.author` lại chờ một truy vấn riêng, tổng thời gian chờ và số lần sử dụng thread có thể tăng nhanh. Khi đó cần xem xét batch loading, DataLoader hoặc tải quan hệ phù hợp.

## 3. Phân biệt synchronous return và blocking I/O

Hai khái niệm liên quan nhưng không đồng nhất:

- **Synchronous return:** method trả kết quả trực tiếp, thay vì trả một handle bất đồng bộ như `Mono`, `Flux` hoặc `CompletableFuture`.
- **Blocking I/O:** thread phải chờ một thao tác I/O hoặc tài nguyên hoàn tất trước khi tiếp tục.

Ví dụ synchronous nhưng không đáng kể về thời gian chờ:

~~~java
@SchemaMapping(typeName = "Book", field = "displayLabel")
public String displayLabel(Book book) {
    return book.getTitle() + " (" + book.getId() + ")";
}
~~~

Ví dụ synchronous và có thể blocking:

~~~java
@QueryMapping
public List<Book> books() {
    return bookRepository.findAll();
}
~~~

Method thứ hai có thể chờ database. Còn method đầu chủ yếu tính toán từ dữ liệu đã có.

| Đặc điểm | Synchronous, xử lý trong bộ nhớ | Synchronous, blocking I/O |
| --- | --- | --- |
| Kiểu trả về | Giá trị Java thông thường | Giá trị Java thông thường |
| Chờ tài nguyên bên ngoài | Thường không | Có thể có |
| Thread trong lúc method chạy | Thực hiện tính toán | Có thể bị giữ trong lúc chờ |
| Ví dụ | Ghép chuỗi, tính thuộc tính | JPA, JDBC, HTTP client đồng bộ |
| Rủi ro chính | CPU nếu phép tính quá nặng | Thread bị chiếm dụng, pool cạn khi tải tăng |

Vì vậy, không cần chuyển mọi method đồng bộ sang reactive. Cần xác định method đang làm gì và chạy trên loại thread nào.

## 4. Blocking method với Spring MVC

Trong ứng dụng Spring MVC, request thường được xử lý trên servlet thread. Resolver đồng bộ có thể chạy trên thread thực thi đang xử lý request/field. Ví dụ dùng JPA:

~~~java
@Controller
class BookQueryController {

    private final BookRepository bookRepository;

    BookQueryController(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @QueryMapping
    public Book book(@Argument("id") UUID id) {
        return bookRepository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

Đây là cách viết đơn giản và phù hợp với nhiều ứng dụng servlet đang dùng JPA. Trong thời gian truy vấn database, thread phục vụ công việc đó phải chờ.

Rủi ro xuất hiện khi thời gian chờ dài hoặc số request đồng thời tăng:

- Nhiều servlet thread bị giữ trong lúc chờ database.
- Thread pool có thể hết thread sẵn sàng nhận request mới.
- Request mới phải chờ hàng đợi hoặc bị từ chối theo cấu hình server.
- Connection pool database cũng có thể trở thành nút thắt.
- Một query GraphQL có nhiều nested resolver blocking có thể tạo ra nhiều lần chờ I/O.

Dùng Spring MVC không có nghĩa blocking luôn an toàn. Cần giới hạn thời gian truy vấn, cấu hình thread pool và connection pool phù hợp với tải dự kiến.

## 5. Blocking method với Spring WebFlux

Spring WebFlux được thiết kế quanh mô hình non-blocking và event-loop. Một event-loop thread cần xử lý nhiều tác vụ ngắn, vì vậy không nên để nó bị giữ lâu bởi JPA/JDBC hoặc HTTP client đồng bộ.

Ví dụ cần tránh trong đường xử lý WebFlux:

~~~java
@Controller
class BookQueryController {

    private final BookRepository bookRepository;

    BookQueryController(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @QueryMapping
    public Book book(@Argument("id") UUID id) {
        // Nếu chạy trên event-loop, lời gọi JPA blocking
        // có thể giữ thread này trong lúc chờ database.
        return bookRepository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

Không giả định Spring GraphQL tự động chuyển mọi method đồng bộ sang worker thread riêng. Method body đồng bộ chạy trên thread gọi nó; thread thực tế phụ thuộc transport và cấu hình execution. Với WebFlux, hãy thiết kế để công việc blocking không chạy trên event-loop.

Nếu dự án dùng reactive database driver và reactive service, trả về reactive type để không giữ thread trong lúc chờ I/O. Nếu buộc phải dùng thư viện blocking, hãy offload thao tác đó sang scheduler hoặc executor chuyên dùng.

## 6. Dùng reactive return type với nguồn dữ liệu non-blocking

Nếu repository và service đã hỗ trợ reactive, controller có thể trả về `Mono` hoặc `Flux`.

Ví dụ với reactive repository:

~~~java
@Controller
class BookReactiveQueryController {

    private final ReactiveBookRepository bookRepository;

    BookReactiveQueryController(ReactiveBookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @QueryMapping
    public Mono<Book> book(@Argument("id") UUID id) {
        return bookRepository.findById(id);
    }

    @QueryMapping
    public Flux<Book> books() {
        return bookRepository.findAll();
    }
}
~~~

Trong ví dụ này, repository trả về publisher. Controller không gọi `block()` để chờ kết quả. Spring for GraphQL tích hợp reactive return value vào quá trình thực thi GraphQL.

Với Query thông thường, `Mono<Book>` biểu diễn kết quả đơn hoặc không có kết quả. Một `Flux<Book>` trả về từ Query field được thu thập thành danh sách cho response của field; nó không tự biến Query thành luồng nhiều response. Với subscription, publisher có vai trò đặc biệt để phát nhiều response theo thời gian; không nhầm `Flux` của Query với một GraphQL subscription.

Reactive return type chỉ giúp non-blocking nếu phần xử lý phía dưới cũng non-blocking. Bọc một lời gọi JPA đồng bộ trong `Mono` mà không offload nó vẫn có thể block thread gọi publisher.

## 7. Offload thư viện blocking bằng boundedElastic

Khi ứng dụng WebFlux cần tiếp tục dùng JPA hoặc một thư viện blocking, có thể tạo publisher từ callable rồi chuyển việc thực thi sang `Schedulers.boundedElastic()`:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Controller
class BookQueryController {

    private final BookRepository bookRepository;

    BookQueryController(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @QueryMapping
    public Mono<Book> book(@Argument("id") UUID id) {
        return Mono.fromCallable(() ->
                    bookRepository.findById(id)
                            .orElseThrow(() -> new BookNotFoundException(id))
                )
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Các bước:

1. `Mono.fromCallable` tạo publisher từ một thao tác đồng bộ.
2. Callable chưa chạy chỉ vì publisher được tạo.
3. `subscribeOn` chỉ định scheduler thực hiện thao tác khi publisher được subscribe.
4. `boundedElastic` cung cấp nhóm thread phù hợp hơn cho công việc blocking có giới hạn.
5. Khi callable hoàn tất, `Mono` phát giá trị hoặc lỗi để GraphQL tiếp tục xử lý.

Không gọi `block()` bên trong resolver. Cách viết sau làm mất lợi ích của việc trả publisher và có thể giữ thread hiện tại:

~~~java
@QueryMapping
public Book book(@Argument("id") UUID id) {
    return Mono.fromCallable(() -> bookRepository.findById(id).orElseThrow())
            .subscribeOn(Schedulers.boundedElastic())
            .block();
}
~~~

`boundedElastic` có giới hạn tài nguyên và hàng đợi; nó không phải khả năng vô hạn để chạy mọi truy vấn. Với workload blocking lớn hoặc cần cô lập rõ ràng, có thể cấu hình scheduler riêng với giới hạn concurrency phù hợp và theo dõi mức sử dụng.

## 8. Offload bằng CompletableFuture và Executor

Một lựa chọn khác là trả về `CompletableFuture`. Spring for GraphQL hỗ trợ kiểu trả về bất đồng bộ này trong annotated controller.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

import org.springframework.beans.factory.annotation.Qualifier;

@Controller
class BookAsyncQueryController {

    private final BookService bookService;
    private final Executor graphqlExecutor;

    BookAsyncQueryController(
            BookService bookService,
            @Qualifier("graphqlExecutor") Executor graphqlExecutor) {
        this.bookService = bookService;
        this.graphqlExecutor = graphqlExecutor;
    }

    @QueryMapping
    public CompletableFuture<Book> book(@Argument("id") UUID id) {
        return CompletableFuture.supplyAsync(
                () -> bookService.findById(id),
                graphqlExecutor
        );
    }
}
~~~

Executor cần được cấu hình với số thread và hàng đợi có giới hạn. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class GraphQlExecutorConfiguration {

    @Bean("graphqlExecutor")
    Executor graphqlExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(24);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("graphql-blocking-");
        return executor;
    }
}
~~~

Spring quản lý vòng đời khởi tạo và shutdown của bean executor. Các con số chỉ là ví dụ minh họa, không phải giá trị tối ưu cho mọi hệ thống. Cần điều chỉnh theo thời gian I/O, số request đồng thời, connection pool và giới hạn tài nguyên của môi trường triển khai.

Tránh dùng `CompletableFuture.supplyAsync` mà không truyền executor cho tác vụ blocking quan trọng. Khi đó tác vụ có thể chạy trên common ForkJoinPool dùng chung, làm khó kiểm soát tải và ảnh hưởng các công việc khác.

## 9. Không chuyển thread tùy tiện

Chuyển tác vụ blocking sang thread khác có thể giải phóng event-loop, nhưng cũng làm thay đổi một số giả định trong ứng dụng.

### 9.1. Transaction context

Với ứng dụng imperative dùng Spring transaction management, transaction thường gắn với thread thực thi. Nếu bắt đầu một transaction rồi chuyển phần xử lý sang executor khác, không được giả định transaction ban đầu tự động đi theo.

Hãy đặt ranh giới transaction tại service method được gọi trong thread thực hiện nghiệp vụ, hoặc dùng cách quản lý transaction phù hợp với mô hình thực thi. Với reactive transaction, context được quản lý theo Reactor Context thay vì dựa vào thread-local truyền thống.

Không nên mở transaction ở một thread rồi trả `CompletableFuture` để thread khác tiếp tục thao tác database trong transaction đó nếu chưa có thiết kế rõ ràng.

### 9.2. Security context và request context

Security context, tracing context và các thông tin request có thể phụ thuộc cơ chế truyền context. Khi chuyển thread, không giả định `ThreadLocal` tự động được sao chép.

Nếu tác vụ cần principal, tenant hoặc correlation ID, hãy truyền dữ liệu cần thiết một cách rõ ràng hoặc cấu hình context propagation phù hợp. Tránh giữ đối tượng request mutable trong field của controller singleton.

### 9.3. Controller singleton và trạng thái dùng chung

Spring controller thường là singleton. Không lưu source object, argument hoặc kết quả của request vào mutable instance field:

~~~java
// Không nên: request này có thể ghi đè trạng thái của request khác.
private UUID currentBookId;
~~~

Hãy giữ dữ liệu request trong tham số method, biến local hoặc context theo request được framework quản lý.

## 10. Timeout và giới hạn tài nguyên

Một blocking call có thể chờ lâu vì database, HTTP service hoặc filesystem gặp sự cố. Nếu không có timeout, thread có thể bị giữ lâu hơn dự kiến.

Nên cấu hình timeout ở đúng tầng:

- **Database:** query timeout, transaction timeout và connection acquisition timeout.
- **HTTP client:** connect timeout, response/read timeout và giới hạn connection pool.
- **Executor:** giới hạn số thread, queue capacity và chính sách từ chối khi quá tải.
- **Application:** request deadline hoặc timeout phù hợp với SLA của API.
- **GraphQL operation:** giới hạn độ phức tạp, số field hoặc kích thước selection set khi phù hợp với hệ thống.

Timeout ở GraphQL request không nhất thiết tự dừng một lời gọi JDBC hoặc HTTP đang blocking. Tác vụ bên dưới cần có timeout riêng. Tương tự, hủy một `CompletableFuture` không bảo đảm thư viện I/O đã dừng công việc hoặc database đã hủy câu lệnh.

Không tăng thread pool vô hạn để che giấu downstream chậm. Hãy tìm nút thắt, đặt giới hạn và áp dụng backpressure hoặc từ chối tải khi hệ thống đã quá khả năng phục vụ.

## 11. Blocking nested resolver và N+1

GraphQL có thể gọi nested resolver nhiều lần trong một operation. Một method blocking ở nested field làm tăng chi phí chờ theo số lượng source object.

Ví dụ:

~~~graphql
query {
    books {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

Nếu `Query.books` trả về 100 sách và mỗi lần resolve `Book.author` đều gọi một truy vấn JPA, hệ thống có thể thực hiện 100 truy vấn riêng cho tác giả. Mỗi truy vấn đều có thể giữ thread trong lúc chờ database.

Có thể gom tải dữ liệu bằng `@BatchMapping`:

~~~java
@Controller
class BookBatchController {

    private final AuthorService authorService;

    BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findAuthorsByBooks(books);
    }
}
~~~

Service có thể truy vấn theo tập `authorId` và trả về map tương ứng. Cách này giảm số lần gọi I/O và thời gian thread bị giữ. DataLoader cũng có thể dùng để gom key và cache trong phạm vi request.

Batching không tự làm truy vấn non-blocking. Nếu batch service vẫn dùng JPA đồng bộ, nó vẫn là blocking call, nhưng số lần gọi database có thể ít hơn đáng kể. Nếu chạy trên WebFlux, vẫn cần offload batch call hoặc dùng reactive data access.

## 12. Xử lý lỗi từ blocking method

Một blocking resolver có thể ném exception trực tiếp:

~~~java
@QueryMapping
public Book book(@Argument("id") UUID id) {
    return bookRepository.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

Exception xảy ra trong quá trình resolve field được chuyển qua cơ chế xử lý lỗi GraphQL của ứng dụng, chẳng hạn `DataFetcherExceptionResolver` hoặc `@GraphQlExceptionHandler`.

Nếu resolver trả `CompletableFuture`, exception có thể xuất hiện dưới dạng exceptional completion. Với `Mono`, lỗi được phát dưới dạng error signal. Dù kiểu trả về khác nhau, ứng dụng vẫn cần ánh xạ lỗi nghiệp vụ và lỗi hạ tầng một cách nhất quán.

GraphQL có thể trả partial data nếu một field lỗi trong khi các field khác thành công. Nếu field lỗi có kiểu non-null, lỗi có thể lan lên field cha theo quy tắc null propagation. Không nên bắt mọi exception rồi trả `null` để che giấu lỗi database hoặc lỗi hệ thống.

## 13. Quan sát hiệu năng của blocking resolver

Để biết blocking method có gây vấn đề hay không, cần quan sát cả GraphQL và hạ tầng bên dưới.

| Nhóm | Chỉ số cần theo dõi |
| --- | --- |
| Resolver | Thời gian thực thi theo field, số lần gọi và tỷ lệ lỗi |
| Servlet/executor | Thread đang hoạt động, thread chờ, queue depth và rejected task |
| WebFlux | Event-loop bị block, độ trễ event-loop và cảnh báo blocking |
| Database | Query latency, active connection, pending acquisition và timeout |
| HTTP client | Connection pool usage, pending request và response latency |
| GraphQL | Operation duration, số field được resolve và lỗi theo path |

Nên ghi nhận operation name, field path hoặc correlation ID khi có thể. Tránh ghi nguyên variables hoặc payload có dữ liệu cá nhân, token hay thông tin bí mật vào log.

Nếu thời gian operation cao, hãy tách thời gian resolver, database và downstream HTTP để xác định phần nào thực sự đang chờ. Tăng thread pool trước khi hiểu nguyên nhân có thể làm tăng áp lực lên database mà không cải thiện throughput.

## 14. Kiểm thử blocking resolver

Có thể dùng `GraphQlTester` để kiểm tra operation đồng bộ:

~~~java
graphQlTester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "book-42")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

Với resolver gọi repository, có thể mock service hoặc repository và xác minh được gọi đúng số lần. Với nested field, hãy kiểm tra số lần gọi để phát hiện N+1 trong test có nhiều source object.

Các tình huống nên kiểm thử:

- Method trả object trực tiếp.
- Blocking service ném exception và lỗi được ánh xạ đúng.
- Database hoặc HTTP timeout tạo response lỗi phù hợp.
- Resolver bất đồng bộ hoàn tất thành công và truyền lỗi đúng.
- Blocking call được offload khỏi event-loop trong cấu hình WebFlux.
- Batch resolver giảm số lần gọi repository.
- Non-null field lỗi gây null propagation như schema dự kiến.

Unit test có thể xác minh logic method. Integration test qua `GraphQlTester` xác minh schema, mapping và GraphQL response. Để kiểm tra event-loop, thread pool hoặc timeout, cần test ở mức integration phù hợp với transport và runtime được triển khai.

## 15. Chọn blocking hay asynchronous/reactive?

Không phải ứng dụng nào cũng cần reactive. Hãy chọn theo stack và đặc tính I/O:

| Tình huống | Hướng phù hợp |
| --- | --- |
| Spring MVC hiện có dùng JPA và tải được kiểm soát | Synchronous resolver có thể phù hợp |
| Resolver chỉ tính toán từ dữ liệu đã có | Trả giá trị Java trực tiếp |
| Spring WebFlux với R2DBC hoặc reactive HTTP client | Trả `Mono`/`Flux`, không block |
| WebFlux nhưng phải gọi JPA/JDBC | Offload bằng bounded scheduler hoặc executor có giới hạn |
| Tác vụ blocking cần executor riêng | Trả `CompletableFuture` dùng executor được cấu hình |
| Nested resolver tạo N+1 | Dùng `@BatchMapping` hoặc DataLoader |
| Công việc CPU nặng | Dùng executor phù hợp với CPU workload, không mặc định dùng boundedElastic |

Một số nguyên tắc thực tế:

- Không chuyển method sang reactive chỉ để đổi kiểu trả về nếu bên dưới vẫn blocking.
- Không gọi `block()` trong resolver WebFlux.
- Không dùng event-loop để chờ JPA/JDBC hoặc HTTP client đồng bộ.
- Không dùng thread pool không giới hạn.
- Đặt timeout cho downstream I/O.
- Đo hiệu năng trước và sau khi thay đổi mô hình thực thi.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| WebFlux chậm khi tải tăng | Resolver đồng bộ gọi JPA/JDBC trên thread không phù hợp | Dùng reactive data access hoặc offload blocking call |
| Đổi `Book` thành `Mono<Book>` nhưng vẫn block | Gọi `block()` hoặc thực hiện I/O trước khi tạo publisher | Đưa lời gọi vào publisher và offload đúng scheduler |
| Thread pool bị cạn | I/O chậm, concurrency cao hoặc pool không có giới hạn phù hợp | Đặt timeout, giới hạn queue và kiểm tra downstream |
| `CompletableFuture` gây tải khó kiểm soát | Dùng common pool hoặc executor không giới hạn | Truyền executor chuyên dụng có giới hạn |
| Transaction không còn hiệu lực sau khi chuyển thread | Dựa vào transaction thread-local ở thread ban đầu | Đặt transaction trong service được gọi trên thread thực thi |
| Security context bị mất | Chuyển thread nhưng không truyền context | Cấu hình context propagation hoặc truyền dữ liệu cần thiết |
| Query GraphQL có nhiều lần chờ database | Nested resolver tạo N+1 | Dùng `@BatchMapping` hoặc DataLoader |
| Hủy request nhưng I/O vẫn chạy | Hủy future không dừng được thư viện blocking | Cấu hình timeout và cancellation ở tầng client/database |
| Không biết resolver nào gây chậm | Chỉ đo tổng thời gian request | Đo duration theo field, database và downstream |

## 17. Quy trình triển khai blocking resolver

Khi viết một resolver có khả năng thực hiện I/O, hãy đi theo trình tự:

1. **Xác định loại công việc.** Method chỉ tính toán trong bộ nhớ hay phải chờ I/O?
2. **Xác định transport/runtime.** Ứng dụng dùng Spring MVC hay Spring WebFlux?
3. **Chọn kiểu trả về.** Dùng giá trị Java cho xử lý đồng bộ, reactive type cho nguồn non-blocking hoặc future khi cần executor.
4. **Kiểm tra thread thực thi.** Không giả định framework tự offload method đồng bộ.
5. **Offload nếu cần.** Với WebFlux và thư viện blocking, dùng bounded scheduler hoặc executor được giới hạn.
6. **Đặt timeout.** Cấu hình ở database, HTTP client và executor.
7. **Rà soát transaction và context.** Kiểm tra transaction, security và tracing khi chuyển thread.
8. **Tìm N+1.** Dùng batch loading nếu nested resolver lặp I/O theo từng source.
9. **Kiểm thử lỗi và tải.** Bao gồm timeout, exceptional completion, pool saturation và null propagation.
10. **Theo dõi production.** Đo resolver latency, thread pool và downstream resource trước khi điều chỉnh cấu hình.

## 18. Tổng kết

Blocking method là method đồng bộ mà thread thực thi phải chờ thao tác bên ngoài như JPA/JDBC, HTTP client hoặc filesystem hoàn tất. Spring for GraphQL hỗ trợ resolver trả giá trị Java trực tiếp; cách này thường phù hợp với ứng dụng Spring MVC dùng thư viện blocking khi tải và thời gian I/O được kiểm soát.

Với Spring WebFlux, không nên để thao tác blocking giữ event-loop. Hãy ưu tiên reactive data access và trả `Mono`/`Flux`; nếu buộc phải dùng thư viện blocking, offload sang bounded scheduler hoặc executor có giới hạn và không gọi `block()` trong resolver. Chuyển thread còn ảnh hưởng transaction, security context và tracing nên cần thiết kế rõ. Kết hợp timeout, batch loading, kiểm thử và quan sát thread pool giúp resolver ổn định khi tải tăng.

