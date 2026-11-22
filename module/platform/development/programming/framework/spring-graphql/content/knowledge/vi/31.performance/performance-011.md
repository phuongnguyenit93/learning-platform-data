# Blocking resolver và thread pool

Một GraphQL operation có thể gọi nhiều resolver để lấy dữ liệu cho các field lồng nhau. Nếu resolver gọi JDBC, JPA, thư viện HTTP đồng bộ hoặc một SDK có thao tác chờ I/O, thread thực thi sẽ bị giữ lại cho tới khi thao tác hoàn tất. Khi nhiều request đến cùng lúc, các thread xử lý request có thể bị chiếm hết, làm tăng thời gian chờ và giảm throughput.

Trong Spring for GraphQL, cần hiểu rõ resolver nào đang chạy đồng bộ, resolver nào trả về kết quả bất đồng bộ và công việc blocking được chuyển sang executor nào. **Thread pool** giúp cô lập các tác vụ blocking và giới hạn số công việc chạy đồng thời. Nó không tự làm cho một thư viện blocking trở thành non-blocking và cũng không thay thế việc tối ưu query, batch loading hoặc connection pool.

Bài này giải thích thread model của GraphQL Java, sự khác nhau giữa Spring MVC và WebFlux, cách Spring for GraphQL xử lý DataFetcher đồng bộ và bất đồng bộ, cách dùng Callable, CompletionStage, Reactor và virtual threads, cách cấu hình executor có giới hạn, cách phối hợp với DataLoader, kiểm thử thread thực thi và xử lý tình trạng pool bị bão hòa.

## 1. Blocking resolver là gì?

Resolver là thành phần lấy giá trị cho một field trong GraphQL schema. Trong Spring for GraphQL, một method có thể được đăng ký làm DataFetcher thông qua @QueryMapping, @MutationMapping, @SchemaMapping hoặc @BatchMapping.

Ví dụ một resolver đồng bộ:

~~~java
@Controller
public class BookController {

    private final BookRepository repository;

    public BookController(BookRepository repository) {
        this.repository = repository;
    }

    @QueryMapping
    public Book bookById(@Argument Long id) {
        return repository.findById(id).orElse(null);
    }
}
~~~

Nếu repository dùng JPA/JDBC, lời gọi findById có thể chờ database trả kết quả. Trong thời gian chờ, thread gọi resolver không thể xử lý công việc khác.

Các thao tác thường có tính blocking gồm JDBC/JPA, HTTP client đồng bộ, filesystem, SDK đồng bộ và việc chờ Future bằng get() hoặc join(). Một resolver chỉ đọc thuộc tính đã có trong object thường không cần chuyển sang thread pool. Hãy tập trung vào thao tác có thể chờ I/O hoặc chiếm CPU đáng kể.

## 2. Thread model của GraphQL Java

Spring for GraphQL sử dụng GraphQL Java để thực thi operation. Query thường dùng AsyncExecutionStrategy, cho phép DataFetcher trả về CompletionStage để các field có thể hoàn tất đồng thời. Tuy nhiên, AsyncExecutionStrategy không tự chuyển mọi method đồng bộ sang thread pool.

Hãy phân biệt hai việc:

1. **Concurrent execution**: nhiều field có thể có các CompletionStage đang chạy cùng lúc.
2. **Thread offloading**: một tác vụ được chuyển sang Executor khác để thread hiện tại không phải chờ tác vụ blocking.

Một DataFetcher trả về Book trực tiếp có thể thực hiện repository call ngay trong lúc GraphQL engine gọi DataFetcher. Nếu muốn tránh giữ thread thực thi GraphQL trong lúc chờ API blocking, cần chuyển tác vụ sang Executor hoặc dùng API non-blocking.

Các field query chỉ có thể tận dụng concurrency khi công việc của chúng được biểu diễn bất đồng bộ, chẳng hạn bằng CompletionStage hoặc reactive publisher. Một resolver đồng bộ vẫn có thể chặn thread trong lúc DataFetcher được gọi.

### Query và mutation có quy tắc thực thi khác nhau

Các field cấp cao nhất của query có thể được thực thi đồng thời theo execution strategy. Các field cấp cao nhất của mutation được thực thi tuần tự để giữ thứ tự mutation. Các field con của một object vẫn được xử lý theo execution strategy tương ứng.

Vì vậy, không nên giả định mọi resolver trong một operation đều chạy song song. Thiết kế resolver cần tính tới loại operation, dependency giữa các field và thứ tự cập nhật dữ liệu.

## 3. Spring MVC và Spring WebFlux

Spring for GraphQL hỗ trợ cả Spring MVC và Spring WebFlux. Cách vận hành thread của hai stack khác nhau:

| Stack | Mô hình xử lý | Rủi ro khi resolver blocking |
|---|---|---|
| Spring MVC | Servlet container dùng request thread pool | Chiếm request thread; khi nhiều request cùng chờ I/O, pool có thể cạn |
| Spring WebFlux | Event-loop thread xử lý I/O non-blocking | Blocking event loop có thể làm chậm nhiều request cùng lúc |

### Với Spring MVC

Servlet stack được thiết kế để xử lý các thao tác blocking trên request thread. Một resolver dùng JDBC đồng bộ có thể hoạt động bình thường, nhưng mỗi request đang chờ database sẽ giữ một servlet thread.

Khi tải tăng, số thread có thể trở thành giới hạn. Tăng servlet thread pool vô hạn không giải quyết gốc rễ vì database connection, CPU và memory vẫn có giới hạn.

### Với Spring WebFlux

WebFlux sử dụng event-loop và mô hình non-blocking I/O. Một event-loop thread có thể xử lý nhiều request nếu các handler không chặn thread.

Nếu resolver gọi JPA hoặc JDBC đồng bộ trực tiếp trên event loop, thread đó bị giữ trong suốt thời gian chờ database. Những request khác được giao cho cùng event loop cũng có thể bị trì hoãn.

Với WebFlux, ưu tiên reactive/non-blocking client như WebClient và R2DBC. Nếu bắt buộc dùng thư viện blocking, hãy chuyển riêng phần blocking sang executor phù hợp và trả kết quả bất đồng bộ về GraphQL engine.

Không gọi block(), Future.get() hoặc join() trong resolver WebFlux để chờ kết quả. Những lời gọi này biến luồng xử lý thành blocking và có thể gây nghẽn event loop.

## 4. Chọn kiểu trả về cho resolver

Spring for GraphQL hỗ trợ nhiều kiểu trả về để biểu diễn công việc đồng bộ hoặc bất đồng bộ:

| Kiểu trả về | Cách hoạt động | Trường hợp phù hợp |
|---|---|---|
| T | Trả kết quả đồng bộ | Logic nhanh, không chờ I/O |
| CompletableFuture hoặc CompletionStage | Trả kết quả sẽ hoàn tất trong tương lai | Tác vụ chạy bằng Executor hoặc API trả future |
| Mono hoặc Flux | Reactive publisher | WebFlux, WebClient, R2DBC hoặc nguồn reactive |
| Callable<T> | Spring gọi tác vụ trên Executor đã cấu hình | Resolver blocking cần được offload qua AnnotatedControllerConfigurer |
| Kotlin suspend hoặc Flow | Coroutine được Spring adapter | Ứng dụng Kotlin |

Không chọn kiểu trả về chỉ để có chữ asynchronous trong chữ ký. Điều quan trọng là công việc blocking phải thực sự chạy trên thread phù hợp và không chặn event loop.

### 4.1. Dùng Callable với AnnotatedControllerConfigurer

Spring for GraphQL hỗ trợ resolver trả về Callable. Callable được gửi tới Executor do AnnotatedControllerConfigurer quản lý. Nếu chưa cấu hình Executor, kiểu trả về này không được hỗ trợ.

~~~java
@Controller
public class BookController {

    private final AuthorRepository authorRepository;

    public BookController(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    @SchemaMapping
    public Callable<Author> author(Book book) {
        return () -> authorRepository
                .findById(book.authorId())
                .orElse(null);
    }
}
~~~

Method trả Callable ngay, còn lời gọi repository chạy khi Executor thực thi Callable. Đây là cách rõ ràng để đánh dấu resolver cần chạy bất đồng bộ.

Ví dụ cấu hình standalone:

~~~java
@Configuration
public class GraphQlConfiguration {

    @Bean
    AnnotatedControllerConfigurer controllerConfigurer(
            @Qualifier("graphqlBlockingExecutor") Executor executor) {

        AnnotatedControllerConfigurer configurer =
                new AnnotatedControllerConfigurer();
        configurer.setExecutor(executor);
        return configurer;
    }
}
~~~

Bean AnnotatedControllerConfigurer này được thêm vào GraphQlSource như một RuntimeWiringConfigurer. Trong ứng dụng Spring Boot, starter đã tự tạo configurer. Chỉ tự khai báo bean thay thế khi bạn chủ động quản lý GraphQlSource và biết rõ các cấu hình mặc định cần giữ lại.

Với cấu hình standalone, cần đưa configurer vào builder:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(schemaResource)
        .configureRuntimeWiring(controllerConfigurer)
        .build();
~~~

Các import chính cho ví dụ standalone gồm org.springframework.graphql.data.method.annotation.support.AnnotatedControllerConfigurer, org.springframework.graphql.execution.GraphQlSource, org.springframework.beans.factory.annotation.Qualifier và java.util.concurrent.Executor.

### 4.2. Dùng CompletableFuture với executor riêng

Nếu muốn chọn executor riêng cho từng tác vụ, có thể trả về CompletableFuture:

~~~java
@Controller
public class BookController {

    private final AuthorRepository authorRepository;
    private final Executor graphqlBlockingExecutor;

    public BookController(
            AuthorRepository authorRepository,
            @Qualifier("graphqlBlockingExecutor") Executor graphqlBlockingExecutor) {
        this.authorRepository = authorRepository;
        this.graphqlBlockingExecutor = graphqlBlockingExecutor;
    }

    @SchemaMapping
    public CompletableFuture<Author> author(Book book) {
        return CompletableFuture.supplyAsync(
                () -> authorRepository
                        .findById(book.authorId())
                        .orElse(null),
                graphqlBlockingExecutor);
    }
}
~~~

Ở đây lời gọi repository được đưa vào executor graphqlBlockingExecutor. GraphQL engine nhận CompletionStage và tiếp tục tổng hợp response khi future hoàn tất.

Luôn truyền executor rõ ràng vào supplyAsync. Nếu bỏ tham số executor, CompletableFuture thường dùng ForkJoinPool.commonPool, khiến tác vụ blocking cạnh tranh tài nguyên với các tác vụ khác trong JVM.

### 4.3. Dùng Mono khi cần cô lập một API blocking

Với WebFlux, nếu chưa thể thay thư viện blocking, có thể bọc lời gọi trong Mono.fromCallable và chỉ định scheduler dùng executor:

~~~java
@SchemaMapping
public Mono<Author> author(Book book) {
    return Mono.fromCallable(() ->
                    authorRepository
                            .findById(book.authorId())
                            .orElse(null))
            .subscribeOn(Schedulers.fromExecutor(graphqlBlockingExecutor));
}
~~~

Callable bên trong Mono chỉ chạy khi publisher được subscribe và được chuyển sang scheduler chỉ định. Không gọi block() sau đoạn code này.

Nếu repository đã dùng R2DBC hoặc service trả Mono từ WebClient, không cần bọc lại bằng fromCallable hay chuyển sang executor blocking. Hãy trả publisher reactive trực tiếp để tận dụng non-blocking I/O.

## 5. Cấu hình ThreadPoolTaskExecutor

Với tác vụ blocking, nên dùng executor có giới hạn rõ ràng. ThreadPoolTaskExecutor cho phép cấu hình số thread cốt lõi, số thread tối đa, hàng đợi và tên thread.

Ví dụ:

~~~java
@Configuration
public class GraphQlExecutorConfiguration {

    @Bean("graphqlBlockingExecutor")
    public ThreadPoolTaskExecutor graphqlBlockingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(24);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("graphql-blocking-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
~~~

Các con số trên chỉ là ví dụ để minh họa cấu hình. Pool thực tế cần được chọn dựa trên độ trễ của dependency, số connection database, số request đồng thời và giới hạn tài nguyên của ứng dụng.

Các import chính gồm org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor, org.springframework.context.annotation.Bean và Configuration. Các ví dụ dùng CompletableFuture cần java.util.concurrent.CompletableFuture và Executor; ví dụ dùng Callable cần java.util.concurrent.Callable.

ThreadPoolTaskExecutor khởi động với corePoolSize thread. Khi các thread cốt lõi đều bận, task được đưa vào queue. Khi queue đầy, pool mới tăng số thread lên đến maxPoolSize. Nếu queue tiếp tục đầy khi pool đã đạt max, task bị từ chối theo rejection policy.

Đặt queueCapacity hữu hạn để giới hạn lượng công việc đang chờ. Queue quá lớn có thể khiến request chờ lâu trong hàng đợi dù không còn thread rảnh, làm tăng latency và giữ nhiều object trong memory.

Không dựa vào cấu hình mặc định của ThreadPoolTaskExecutor cho workload production. Mặc định core pool nhỏ, max pool rất lớn và queue capacity không giới hạn; queue không giới hạn có thể khiến maxPoolSize không được dùng để mở rộng như mong đợi.

### Cấu hình Spring Boot

Spring Boot GraphQL starter tự cấu hình AnnotatedControllerConfigurer và dùng applicationTaskExecutor nếu có. Với cấu hình mặc định của Boot, Callable return values của controller được gửi tới executor này.

Nếu muốn thay executor dùng chung của Boot, có thể khai báo bean tên applicationTaskExecutor:

~~~java
@Bean(name = "applicationTaskExecutor")
public ThreadPoolTaskExecutor applicationTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(24);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("application-");
    return executor;
}
~~~

Lưu ý applicationTaskExecutor có thể được dùng bởi các tích hợp Spring khác như Spring MVC, WebFlux, WebSocket và tác vụ bất đồng bộ. Khi thay bean này, hãy tính tổng tải của các thành phần dùng chung pool.

Nếu chỉ muốn executor dành riêng cho một resolver hoặc một nhóm tác vụ GraphQL, có thể inject graphqlBlockingExecutor và truyền trực tiếp vào CompletableFuture.supplyAsync như ví dụ trước. Cách này không yêu cầu thay executor dùng chung của ứng dụng.

### Cấu hình standalone

Khi tự tạo AnnotatedControllerConfigurer, gọi setExecutor với executor muốn dùng cho Callable. Bean configurer cần được thêm vào GraphQlSource như một RuntimeWiringConfigurer. Với Spring Boot, không tạo thêm configurer thứ hai nếu starter đã cung cấp configurer mặc định.

## 6. Virtual threads trên Java 21+

Virtual threads cho phép ứng dụng tạo nhiều thread nhẹ hơn platform thread, phù hợp với workload I/O blocking có nhiều thời gian chờ. Chúng giúp tận dụng thời gian chờ I/O, nhưng không làm database nhanh hơn và không tăng số connection mà database cho phép.

Với Java 21 trở lên và Spring Boot hỗ trợ virtual threads (ví dụ Spring Boot 3.2+), có thể bật:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
~~~

Spring Boot có thể cấu hình applicationTaskExecutor sử dụng virtual threads. Spring Boot GraphQL starter cũng cấu hình AnnotatedControllerConfigurer với executor đó. Từ Spring for GraphQL 1.3, khi AnnotatedControllerConfigurer có Executor và chạy trên Java 21+, các controller method có chữ ký blocking có thể được gọi bất đồng bộ. Các kiểu trả về async như Mono, Flux, CompletableFuture và Kotlin suspending function không bị xem là blocking method theo quy tắc mặc định.

AnnotatedControllerConfigurer cũng cho phép tùy chỉnh blocking method predicate nếu quy tắc nhận diện mặc định không phù hợp với controller của ứng dụng.

Với hỗ trợ này, method có thể trả trực tiếp T thay vì phải bọc trong Callable. Tuy nhiên, hãy xác minh phiên bản Spring Boot và Spring for GraphQL của ứng dụng, vì hành vi này phụ thuộc phiên bản và cấu hình executor.

Virtual threads phù hợp với I/O blocking. Công việc CPU-bound vẫn bị giới hạn bởi số core CPU; tạo thêm nhiều virtual thread không làm tăng năng lực tính toán. Connection pool, giới hạn API bên ngoài và semaphore vẫn cần được quản lý.

## 7. Chọn kích thước thread pool

Không có một con số corePoolSize hoặc maxPoolSize đúng cho mọi GraphQL service. Hãy chọn dựa trên loại công việc và giới hạn của hệ thống phía sau.

### Công việc CPU-bound

Nếu resolver thực hiện tính toán nặng, số thread chạy đồng thời nên gần với số CPU core mà container hoặc máy chủ thực sự được cấp. Tăng số thread quá nhiều có thể làm tăng context switching và khiến thời gian xử lý dài hơn.

### Công việc I/O-bound

Nếu resolver thường chờ database hoặc remote API, có thể cần nhiều thread hơn số CPU core để tận dụng thời gian chờ. Tuy nhiên, giới hạn thực tế thường nằm ở database connection pool, rate limit của remote API, socket và memory.

Ví dụ, nếu database chỉ cấp 20 connection cho ứng dụng nhưng executor có thể chạy 100 truy vấn JDBC cùng lúc, phần lớn task có thể chờ connection. Thread pool lớn không làm database xử lý nhanh hơn.

Khi sizing, cần xem xét:

- Số request GraphQL đồng thời.
- Số resolver blocking có thể được gọi trong một request.
- Thời gian trung bình và p95/p99 của database hoặc remote API.
- Kích thước connection pool và giới hạn concurrency của dependency.
- Số CPU core và memory của container.
- Số thread hoặc virtual thread đang hoạt động.
- Độ dài queue và thời gian chờ trước khi task bắt đầu.

Đo dưới tải đại diện rồi điều chỉnh từng thông số. Không lấy số thread của máy phát triển làm cấu hình production.

## 8. Dùng DataLoader để giảm số lần blocking I/O

Thread pool giúp cô lập các thao tác blocking, nhưng nếu mỗi field con thực hiện một query database riêng thì ứng dụng vẫn có thể phát sinh N+1.

Giả sử query lấy 100 sách và mỗi sách có field author. Nếu resolver author gọi repository một lần cho mỗi sách, ứng dụng có thể phát sinh 100 truy vấn bổ sung. Việc chuyển cả 100 truy vấn sang thread pool không loại bỏ chi phí đó; nó chỉ làm 100 thao tác chờ chạy trên executor khác.

Hãy dùng BatchMapping hoặc BatchLoaderRegistry để gom các key thành một lần batch load:

~~~java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping
    public Callable<Map<Book, Author>> author(List<Book> books) {
        return () -> authorService.findAuthorsForBooks(books);
    }
}
~~~

Trong ví dụ, một batch method nhận danh sách Book và trả về Map<Book, Author>. Callable được gửi qua Executor đã cấu hình cho AnnotatedControllerConfigurer. Thay vì chạy một tác vụ blocking cho mỗi sách, ứng dụng có thể thực hiện một truy vấn batch.

Nếu batch service đã non-blocking, hãy trả về Mono<Map<Book, Author>> hoặc Flux<Author> theo đúng thứ tự của danh sách đầu vào. Không cần đưa reactive batch load sang executor blocking.

DataLoader có cache theo request. Vì vậy, tránh tạo một DataLoader hoặc một executor riêng cho từng field invocation. Dùng BatchLoaderRegistry do Spring quản lý để đăng ký loader và giữ đúng phạm vi request.

## 9. Queue, rejection và backpressure

Thread pool cần một chính sách rõ ràng khi số task vượt quá khả năng xử lý.

| Trạng thái | Hành vi | Ý nghĩa |
|---|---|---|
| Còn thread rảnh | Task chạy ngay | Không cần chờ queue |
| Thread đang bận nhưng queue còn chỗ | Task được xếp hàng | Latency tăng theo thời gian chờ |
| Queue đầy, pool còn khả năng mở rộng | Pool tạo thêm thread tới maxPoolSize | Concurrency tăng, có thể tạo thêm tải lên dependency |
| Pool đạt max và queue đầy | Task bị từ chối | Hệ thống đang quá tải so với giới hạn đã cấu hình |

Không nên dùng queue vô hạn để tránh lỗi từ chối task. Queue vô hạn có thể làm request chờ quá lâu và giữ nhiều dữ liệu trong memory. Khi queue đầy, từ chối có kiểm soát thường dễ vận hành hơn việc để latency tăng không giới hạn.

ThreadPoolTaskExecutor mặc định dùng chính sách từ chối task khi pool và queue đã đầy. Có thể xử lý TaskRejectedException ở tầng phù hợp để trả lỗi có thể quan sát được.

Tránh CallerRunsPolicy cho blocking resolver trong WebFlux. Chính sách này có thể chạy tác vụ trên thread gửi task; nếu thread đó là event loop, blocking I/O sẽ quay lại chặn event loop.

Đặt timeout cho database query và remote client. Timeout của GraphQL request không tự dừng mọi thao tác blocking bên dưới; mỗi dependency vẫn cần timeout riêng và cơ chế hủy phù hợp.

## 10. Transaction và context khi chuyển thread

Khi resolver được chuyển sang executor, công việc chạy trên thread khác với thread nhận request. Một số cơ chế của Spring gắn trạng thái vào ThreadLocal, vì vậy không nên giả định trạng thái đó tự động đi theo task.

### Transaction

Transaction của Spring với transaction manager đồng bộ thường gắn với thread thực thi. Nếu GraphQL request mở transaction trên request thread rồi resolver chạy trên worker thread, worker thread không tự tham gia transaction đó.

Với JDBC/JPA, cách dễ kiểm soát hơn là đặt transaction quanh service method thực hiện truy cập database. Nếu service method được gọi bên trong Callable hoặc CompletableFuture trên worker thread, transaction được mở và đóng trên chính thread đó.

Không nên tạo một transaction đồng bộ bao trùm toàn bộ GraphQL query có nhiều DataFetcher chạy đồng thời. Nếu nghiệp vụ cần một transaction xuyên suốt operation, phải thiết kế execution strategy và transaction lifecycle có chủ đích; đây là trường hợp nâng cao vì execution strategy mặc định có thể chạy field trên nhiều thread.

### Security, logging và tracing context

Khi dùng CompletableFuture.supplyAsync với executor tùy chỉnh, ThreadLocal như MDC hoặc observation context có thể không tự được truyền sang worker thread.

Với Spring Framework 6.1 trở lên, có thể cấu hình ContextPropagatingTaskDecorator cho ThreadPoolTaskExecutor:

~~~java
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
~~~

Decorator này dùng Micrometer Context Propagation để khôi phục các context accessor đã đăng ký trong lúc task chạy. Với SecurityContext hoặc context riêng của ứng dụng, hãy xác minh integration tương ứng hoặc truyền dữ liệu cần thiết một cách tường minh. Không truyền toàn bộ request object sang thread khác nếu chỉ cần một vài giá trị.

Class ContextPropagatingTaskDecorator thuộc package org.springframework.core.task.support và có từ Spring Framework 6.1.

GraphQLContext là nơi phù hợp để truyền dữ liệu theo request trong GraphQL execution. Với DataLoader, ưu tiên BatchLoaderRegistry của Spring để nhận context và hỗ trợ context propagation theo cơ chế của framework.

## 11. Kiểm thử blocking resolver

Một test hữu ích cần xác minh hai điều: response GraphQL vẫn đúng và phần blocking thực sự chạy trên executor dự kiến.

Ví dụ controller lưu lại tên thread đã thực thi resolver:

~~~java
@Controller
public class DiagnosticsController {

    private final AtomicReference<String> lastThreadName =
            new AtomicReference<>();

    @QueryMapping
    public Callable<String> resolverThread() {
        return () -> {
            lastThreadName.set(Thread.currentThread().getName());
            return "ok";
        };
    }

    public String getLastThreadName() {
        return lastThreadName.get();
    }
}
~~~

Sau khi gửi query bằng GraphQlTester, kiểm tra response và tên thread:

~~~java
graphQlTester.document("{ resolverThread }")
        .execute()
        .path("resolverThread")
        .entity(String.class)
        .isEqualTo("ok");

assertThat(diagnosticsController.getLastThreadName())
        .startsWith("graphql-blocking-");
~~~

Test này cần cấu hình AnnotatedControllerConfigurer với executor có threadNamePrefix tương ứng. Nếu resolver chạy trên request thread, test sẽ phát hiện cấu hình offload chưa được áp dụng.

Các import chính của ví dụ gồm java.util.concurrent.Callable, java.util.concurrent.atomic.AtomicReference, org.springframework.graphql.data.method.annotation.QueryMapping, org.springframework.graphql.test.tester.GraphQlTester và static import các assertion của AssertJ.

Ngoài test trên, nên kiểm tra:

1. Query có nhiều field bất đồng bộ trả response đầy đủ.
2. Resolver ném exception được chuyển thành GraphQL error phù hợp.
3. Callable hoặc future bị timeout có hành vi được xác định.
4. Queue đầy dẫn tới rejection có thể quan sát, không làm request treo vô hạn.
5. Số task chạy đồng thời không vượt giới hạn đã đặt.
6. DataLoader batch được gọi với số key dự kiến.
7. Context cần thiết như trace ID hoặc thông tin người dùng vẫn có khi task chạy trên worker thread.

Không chỉ kiểm thử trên một request đơn lẻ. Hãy chạy thử tải đồng thời để quan sát queue, active thread, response latency và tỷ lệ task bị từ chối.

## 12. Theo dõi thread pool khi ứng dụng chạy

Khi vận hành, cần theo dõi cả GraphQL request và executor thực thi blocking task.

Các chỉ số nên quan sát:

| Chỉ số | Dùng để phát hiện |
|---|---|
| Active thread count | Số thread đang thực hiện task |
| Pool size | Số thread hiện có trong pool |
| Queue size | Số task đang chờ được thực thi |
| Completed task count | Tổng số task đã hoàn tất |
| Rejected task count | Số task bị từ chối khi pool quá tải |
| Task queue wait time | Thời gian task nằm chờ trước khi chạy |
| Task execution time | Thời gian thực thi tác vụ blocking |
| GraphQL p95/p99 latency | Ảnh hưởng của pool tới thời gian trả response |

ThreadPoolTaskExecutor cung cấp thông tin như pool size và active count. Có thể expose các chỉ số này qua JMX hoặc metrics tùy cách cấu hình ứng dụng. Với Spring Boot Actuator, nên theo dõi chúng cùng metric của servlet/event-loop, database connection pool và HTTP client pool.

Nếu active thread luôn bằng maxPoolSize và queue liên tục tăng, executor đang bão hòa. Nếu queue thấp nhưng database connection pool luôn cạn, nút thắt có thể nằm ở database hoặc thời gian giữ connection. Nếu executor rảnh nhưng GraphQL request vẫn chậm, hãy kiểm tra resolver, network và các dependency khác.

Không chỉ nhìn số thread. Queue wait time và thời gian thực thi giúp phân biệt task chậm do phải chờ được chạy với task chậm do chính dependency.

## 13. Những lỗi thường gặp với blocking resolver và thread pool

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| WebFlux chậm bất thường khi gọi JPA | Resolver blocking đang chạy trên event loop | Dùng R2DBC hoặc offload phần blocking sang executor |
| Có AsyncExecutionStrategy nhưng request vẫn bị block | Resolver trả T đồng bộ và thực hiện I/O trước khi trả kết quả | Trả CompletionStage, Mono hoặc Callable chạy trên executor |
| Callable bị lỗi khi đăng ký controller | AnnotatedControllerConfigurer chưa có Executor | Cấu hình Executor trên configurer |
| Resolver không chạy trên thread pool mong muốn | CompletableFuture dùng commonPool hoặc executor chưa được truyền | Truyền executor rõ ràng vào supplyAsync |
| Pool có queue rất dài | Queue quá lớn hoặc dependency xử lý chậm | Đặt queue hữu hạn, đo queue wait time và kiểm tra dependency |
| Task bị từ chối khi tải tăng | Pool đạt max và queue đã đầy | Điều chỉnh capacity theo tải thực, giới hạn request và xử lý rejection |
| Tăng thread nhưng database không nhanh hơn | Connection pool hoặc database đã bão hòa | Đồng bộ giới hạn executor với connection pool và tối ưu query |
| Resolver con tạo quá nhiều query | N+1, mỗi field blocking riêng | Dùng BatchMapping hoặc BatchLoaderRegistry |
| Trace ID hoặc MDC bị mất trên worker thread | Context không được truyền qua executor tùy chỉnh | Cấu hình context propagation hoặc truyền dữ liệu tường minh |
| Transaction không bao trùm resolver offload | Transaction gắn với thread request, resolver chạy ở thread khác | Đặt transaction quanh service method chạy trên worker thread |
| CPU tăng khi tăng số thread | Workload CPU-bound hoặc context switching quá nhiều | Giảm concurrency và tối ưu thuật toán |
| Resolver timeout nhưng JDBC vẫn tiếp tục chạy | Timeout GraphQL không dừng được lệnh JDBC | Cấu hình query timeout và cancellation ở dependency |

## 14. Quy trình triển khai blocking resolver

Khi một resolver cần gọi thư viện blocking:

1. Xác định thao tác nào thực sự blocking và đo thời gian chờ của nó.
2. Nếu có thể, thay bằng API non-blocking như WebClient hoặc R2DBC.
3. Nếu phải giữ thư viện blocking, chọn một executor có giới hạn.
4. Dùng Callable với AnnotatedControllerConfigurer, hoặc dùng CompletableFuture.supplyAsync với executor được truyền rõ ràng.
5. Với WebFlux, không gọi block() trên event loop; chuyển riêng phần blocking sang scheduler phù hợp.
6. Cấu hình corePoolSize, maxPoolSize và queueCapacity theo giới hạn của dependency.
7. Đặt timeout cho database và remote API.
8. Dùng BatchMapping hoặc BatchLoaderRegistry để giảm N+1.
9. Xác minh transaction được mở trên đúng thread thực thi service.
10. Cấu hình context propagation nếu cần trace ID, MDC hoặc context khác trên worker thread.
11. Kiểm thử response, thread name, concurrency, rejection và timeout.
12. Theo dõi active thread, queue size, queue wait time, dependency pool và GraphQL latency dưới tải thực tế.

Blocking resolver không phải lúc nào cũng cần thread pool. Với Spring MVC, blocking trên request thread có thể là lựa chọn chấp nhận được nếu tải và giới hạn servlet pool phù hợp. Với WebFlux, tránh blocking event loop là yêu cầu quan trọng. Khi cần offload, hãy dùng Executor có giới hạn hoặc virtual threads trên Java 21+ với cấu hình Spring hỗ trợ. Kết hợp thread pool với DataLoader, timeout và đo lường runtime để kiểm soát concurrency từ GraphQL resolver tới database và dịch vụ bên ngoài.

## Tài liệu tham khảo

- Spring for GraphQL — Request Execution và Thread Model: https://docs.spring.io/spring-graphql/reference/request-execution.html
- Spring for GraphQL — Annotated Controllers và Callable: https://docs.spring.io/spring-graphql/reference/controllers.html
- Spring Boot — Task Execution and Scheduling: https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring for GraphQL — Batch Loading: https://docs.spring.io/spring-graphql/reference/request-execution.html#execution-batch-loading
