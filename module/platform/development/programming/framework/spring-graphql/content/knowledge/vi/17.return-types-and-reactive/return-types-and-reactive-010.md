# Executor cho blocking controller trong Spring for GraphQL

Annotated controller của Spring for GraphQL có thể trả về giá trị đồng bộ như `Book`, `List<Book>` hoặc `String`. Với các handler gọi JDBC, JPA, HTTP client đồng bộ hoặc API I/O chặn, method có thể giữ thread đang thực thi GraphQL trong suốt thời gian chờ. Cấu hình `Executor` trên `AnnotatedControllerConfigurer` cho phép Spring chạy các handler blocking trên thread riêng.

Có hai cơ chế cần phân biệt:

- `Callable<T>` được gửi đến `Executor` để phần công việc bên trong `Callable` chạy bất đồng bộ. Cơ chế này có thể dùng trên các phiên bản Java khác nhau khi `Executor` đã được cấu hình.
- Từ Spring for GraphQL 1.3 trên Java 21+, khi có `Executor`, các controller method có chữ ký blocking có thể được tự động gọi bất đồng bộ dù method trả trực tiếp `T`. Đây là cơ chế phù hợp để giữ controller đồng bộ khi đang dùng thư viện blocking.

Spring Boot starter có thể tự cấu hình `Executor` dùng virtual thread khi bật `spring.threads.virtual.enabled`. Bài này giải thích cách hoạt động, cấu hình, lựa chọn executor, kiểm thử và các giới hạn cần quan tâm.

## 1. Vì sao blocking controller cần Executor?

GraphQL thường resolve nhiều field trong cùng một operation. Ví dụ query:

~~~graphql
query BookDetails($id: ID!) {
    book(id: $id) {
        id
        title
        author {
            id
            name
        }
        reviews {
            id
            comment
        }
    }
}
~~~

Resolver của `book`, `author` và `reviews` có thể truy cập các nguồn dữ liệu khác nhau. Nếu các handler dùng API đồng bộ, mỗi lần gọi database hoặc HTTP client có thể giữ thread cho đến khi I/O hoàn tất.

Ví dụ một controller blocking:

~~~java
@Controller
public class BookController {

    private final BookRepository bookRepository;

    public BookController(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @QueryMapping
    public Book book(@Argument("id") Long id) {
        return bookRepository.findById(id).orElse(null);
    }
}
~~~

`findById` của Spring Data JPA là lời gọi đồng bộ. Khi handler chạy trên thread xử lý request, thread đó phải chờ database trả kết quả. Nếu nhiều request cùng lúc đều chờ I/O, số thread phục vụ request có thể trở thành giới hạn thông lượng.

Executor tạo một ranh giới thực thi riêng cho các handler được xem là blocking. GraphQL vẫn nhận kết quả của data fetcher theo cơ chế bất đồng bộ, trong khi controller có thể tiếp tục viết theo phong cách imperative quen thuộc.

## 2. Vai trò của AnnotatedControllerConfigurer

`AnnotatedControllerConfigurer` phát hiện các bean `@Controller`, tìm method được annotate bằng `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping`, `@SchemaMapping` hoặc `@BatchMapping`, rồi đăng ký chúng thành GraphQL `DataFetcher`.

Lớp này có method `setExecutor(Executor)` để cấu hình executor cho:

- Giá trị trả về `Callable<T>` từ controller method.
- Các controller method có chữ ký blocking trên Java 21+ khi phiên bản Spring for GraphQL hỗ trợ cơ chế tự động offload và executor không khai báo ưu tiên tác vụ ngắn.

Khi không có executor, controller method blocking được gọi đồng bộ. `Callable` cũng không được hỗ trợ nếu configurer chưa có executor.

~~~mermaid
flowchart TD
    A[GraphQL operation] --> B[GraphQL DataFetcher]
    B --> C[AnnotatedControllerConfigurer]
    C --> D{Controller method type}
    D -->|Reactive: Mono / Flux / CompletionStage| E[Return async value]
    D -->|Blocking signature on Java 21+ with Executor| F[Submit invocation to Executor]
    D -->|Callable with Executor| G[Submit Callable to Executor]
    D -->|Synchronous without Executor or older Java| H[Invoke on current thread]
    E --> I[GraphQL async execution]
    F --> I
    G --> I
    H --> I
~~~

Sơ đồ thể hiện các nhánh chính. Việc một method có được xem là blocking hay không phụ thuộc vào loại giá trị trả về và cấu hình `blockingMethodPredicate` của `AnnotatedControllerConfigurer`.

## 3. Các loại return type và cách thực thi

| Return type | Cách thực thi |
| --- | --- |
| `T` như `Book`, `String`, `List<Book>` | Mặc định được gọi đồng bộ. Trên Java 21+ với executor phù hợp cho tác vụ blocking, method có chữ ký blocking có thể được offload tự động |
| `Callable<T>` | Phần công việc trong `Callable` được gửi đến executor; cần cấu hình executor |
| `CompletableFuture<T>` | Method tự cung cấp kết quả bất đồng bộ; không được xem là blocking theo predicate mặc định |
| `Mono<T>`, `Flux<T>` | Dùng mô hình reactive; Spring for GraphQL chuyển đổi kết quả sang cơ chế async của GraphQL Java |
| Kotlin `suspend` hoặc `Flow` | Được thích nghi sang kiểu reactive tương ứng |

Một điểm dễ nhầm: chỉ khai báo `Executor` không làm mọi method trở thành bất đồng bộ trên mọi phiên bản Java. Tự động offload method trả về `T` yêu cầu Java 21+ và Spring for GraphQL 1.3+. Trên phiên bản cũ hơn, có thể dùng `Callable<T>` để gửi phần blocking work đến executor.

## 4. Cấu hình virtual threads với Spring Boot

Với ứng dụng Spring Boot dùng Spring for GraphQL starter, cách cấu hình ngắn nhất là bật virtual threads:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
~~~

Yêu cầu Java 21 trở lên. Spring Boot tự cấu hình `AsyncTaskExecutor` dựa trên `SimpleAsyncTaskExecutor` dùng virtual threads và Spring for GraphQL starter cấu hình `AnnotatedControllerConfigurer` sử dụng executor đó. Trên Spring for GraphQL 1.3+ với Java 21+, các controller method có chữ ký blocking được gọi bất đồng bộ.

Ví dụ controller vẫn trả về `Book` trực tiếp:

~~~java
@Controller
public class BookController {

    private final BookRepository repository;

    public BookController(BookRepository repository) {
        this.repository = repository;
    }

    @QueryMapping
    public Book book(@Argument("id") Long id) {
        // Synchronous JPA call, invoked asynchronously on a virtual thread
        // when the runtime and configuration support blocking invocation.
        return repository.findById(id).orElse(null);
    }
}
~~~

Không cần đổi method thành `Callable<Book>` chỉ để dùng virtual thread khi automatic blocking invocation đã được hỗ trợ. Việc giữ return type trực tiếp cũng giúp chữ ký method phản ánh dữ liệu mà resolver trả về.

Virtual threads là tính năng của JVM, không phải một cách làm cho JDBC hoặc HTTP client trở thành non-blocking. Chúng giúp một ứng dụng phục vụ nhiều tác vụ I/O đang chờ với chi phí thread thấp hơn so với tạo nhiều platform thread.

## 5. Dùng Callable với Executor

`Callable<T>` là lựa chọn tường minh khi muốn xác định phần công việc được gửi đến executor:

~~~java
import java.util.concurrent.Callable;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookRepository repository;

    public BookController(BookRepository repository) {
        this.repository = repository;
    }

    @QueryMapping
    public Callable<Book> book(@Argument("id") Long id) {
        return () -> repository.findById(id).orElse(null);
    }
}
~~~

Method tạo và trả về `Callable` trên thread đang gọi controller; phần gọi repository nằm bên trong lambda và được executor thực thi. Executor phải được cấu hình trên `AnnotatedControllerConfigurer`, nếu không `Callable` return type không được hỗ trợ.

`Callable` hữu ích khi:

- Ứng dụng chạy trên Java thấp hơn 21 nhưng cần tách blocking work khỏi thread hiện tại.
- Muốn đánh dấu rõ phần công việc cần chạy bất đồng bộ.
- Chỉ một số resolver cần chuyển sang executor, hoặc chưa thể bật cơ chế offload tự động.

Không nên trả về `Callable` chỉ để bọc một phép tính nhỏ không blocking. Việc submit task, chuyển kết quả và xử lý lỗi có chi phí; chỉ dùng khi có lý do về thực thi.

## 6. Dùng ThreadPoolTaskExecutor tùy chỉnh trong Spring Boot

Spring Boot tự cấu hình executor mặc định. Nếu cần điều chỉnh giới hạn pool và queue cho ứng dụng, có thể khai báo một `AsyncTaskExecutor` tên `applicationTaskExecutor`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class GraphQlExecutorConfiguration {

    @Bean(name = "applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("graphql-blocking-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
~~~

Spring Boot dùng bean `applicationTaskExecutor` cho các tích hợp task execution tương ứng, trong đó có việc thực thi `Callable` của Spring for GraphQL. Spring Boot GraphQL auto-configuration cũng lấy executor này để cấu hình `AnnotatedControllerConfigurer`.

Lưu ý về automatic blocking invocation: `ThreadPoolTaskExecutor` triển khai `SchedulingTaskExecutor` và mặc định báo rằng nó ưu tiên tác vụ ngắn. Spring for GraphQL dùng gợi ý `prefersShortLivedTasks` khi quyết định có offload method blocking trả trực tiếp `T` hay không. Vì vậy, thread pool ở ví dụ này phù hợp để chạy `Callable<T>`; không nên mặc định nó sẽ offload các method đồng bộ trả về `T`. Với method trả trực tiếp `T`, dùng virtual-thread executor do Spring Boot cấu hình hoặc một executor phù hợp không khai báo ưu tiên tác vụ ngắn.

Tên bean có ý nghĩa khi ứng dụng có nhiều executor. Nếu tự tạo một `Executor` khác với tên riêng, không nên giả định Spring Boot GraphQL sẽ tự chọn nó. Hãy kiểm tra qualifier và cách auto-configuration của đúng phiên bản Spring Boot đang dùng.

Nếu muốn Spring Boot tự dùng virtual threads, không khai báo bean `applicationTaskExecutor` kiểu thread pool như ví dụ này; bean tùy chỉnh sẽ thay thế executor auto-configured. Chọn một cấu hình phù hợp với workload của ứng dụng.

Ví dụ trên dùng thread pool giới hạn. Giá trị `corePoolSize`, `maxPoolSize` và `queueCapacity` chỉ là điểm bắt đầu để minh họa, không phải cấu hình tối ưu chung. Cần đo tải thực tế và căn chỉnh với số kết nối database, giới hạn downstream và mức đồng thời của request.

## 7. Cấu hình trực tiếp AnnotatedControllerConfigurer

Trong ứng dụng không dùng Spring Boot, hoặc khi chủ động thay thế configurer mặc định, có thể tạo bean và gọi `setExecutor`:

~~~java
import java.util.List;

import java.util.concurrent.Executor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.data.method.annotation.support.AnnotatedControllerConfigurer;
import org.springframework.graphql.execution.GraphQlSource;

@Configuration(proxyBeanMethods = false)
public class GraphQlConfiguration {

    @Bean
    AnnotatedControllerConfigurer controllerConfigurer(Executor executor) {
        AnnotatedControllerConfigurer configurer =
                new AnnotatedControllerConfigurer();
        configurer.setExecutor(executor);
        return configurer;
    }
}
~~~

`AnnotatedControllerConfigurer` là một `RuntimeWiringConfigurer`. Khi tự cấu hình `GraphQlSource`, cần đưa configurer vào runtime wiring:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
        .configureRuntimeWiring(controllerConfigurer)
        .exceptionResolvers(List.of(controllerConfigurer.getExceptionResolver()))
        .build();
~~~

Trong Spring Boot, không nên thay thế configurer mặc định chỉ để đặt executor nếu property hoặc executor bean đã đáp ứng nhu cầu. Khi tự khai báo `AnnotatedControllerConfigurer`, ứng dụng chịu trách nhiệm giữ lại các tùy chỉnh cần thiết như custom argument resolvers và exception resolver.

Nếu executor được truyền vào đây là `ThreadPoolTaskExecutor`, hãy dùng nó cho `Callable<T>` hoặc tác vụ ngắn. Để tự động offload method đồng bộ trả về `T` trên Java 21+, chọn executor phù hợp với blocking work theo quy tắc `prefersShortLivedTasks`.

## 8. Chọn method nào được xem là blocking?

Trên Java 21+ khi có executor, Spring for GraphQL mặc định xem controller method là blocking nếu return type không phải một kiểu async đã biết như `Mono`, `Flux`, `CompletableFuture` và method không phải Kotlin suspending function.

`AnnotatedControllerConfigurer` cung cấp `setBlockingMethodPredicate(...)` để tùy chỉnh việc nhận diện method blocking. Predicate nhận `HandlerMethod`, nhờ đó có thể xét annotation, class hoặc tên method theo quy ước ứng dụng. Predicate chỉ quyết định method nào được xem là blocking; executor vẫn phải phù hợp với automatic blocking invocation và không ưu tiên tác vụ ngắn.

Ví dụ đánh dấu rõ resolver blocking bằng annotation riêng:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface BlockingGraphQl {}
~~~

Khi tự cấu hình `AnnotatedControllerConfigurer`, predicate có thể kiểm tra annotation này:

~~~java
configurer.setBlockingMethodPredicate(handlerMethod ->
        handlerMethod.getMethod().isAnnotationPresent(BlockingGraphQl.class)
);
~~~

Ví dụ sử dụng:

~~~java
@QueryMapping
@BlockingGraphQl
public Book book(@Argument("id") Long id) {
    return repository.findById(id).orElse(null);
}
~~~

Predicate tùy chỉnh chỉ cần thiết khi quy tắc mặc định không phù hợp. Cần kiểm tra phiên bản Spring for GraphQL và Java đang dùng vì automatic blocking invocation có điều kiện phiên bản. Trên Java 20 trở xuống, lựa chọn tường minh và tương thích hơn là trả `Callable<T>` khi cần executor.

## 9. Phân biệt Executor với reactive return type

Executor phục vụ controller blocking. Với `Mono` hoặc `Flux`, method đã trả về một publisher đại diện cho công việc bất đồng bộ; Spring for GraphQL thích nghi publisher đó với `CompletionStage` để GraphQL Java xử lý.

Ví dụ reactive:

~~~java
@Controller
public class ReactiveBookController {

    private final ReactiveBookRepository repository;

    public ReactiveBookController(ReactiveBookRepository repository) {
        this.repository = repository;
    }

    @QueryMapping
    public Mono<Book> book(@Argument("id") Long id) {
        return repository.findById(id);
    }
}
~~~

Không cần chuyển một resolver reactive sang `Executor` chỉ vì muốn nó chạy bất đồng bộ. Reactive pipeline nên dùng reactive driver/client phù hợp. Nếu gọi thư viện blocking bên trong reactive pipeline, hãy cô lập phần blocking bằng scheduler phù hợp như `Schedulers.boundedElastic()` hoặc thay thế bằng client non-blocking; đừng giả định `AnnotatedControllerConfigurer` sẽ tự phát hiện blocking nằm bên trong lambda của `Mono`.

| Tình huống | Hướng xử lý |
| --- | --- |
| Resolver dùng JPA/JDBC đồng bộ | Executor cho blocking controller; Java 21+ có thể tự offload chữ ký blocking |
| Resolver trả `Callable<T>` | Cấu hình executor để Callable được submit |
| Resolver dùng R2DBC và trả `Mono<T>` | Giữ reactive return type và reactive I/O |
| Resolver trả `CompletableFuture<T>` | Tự quản lý việc tạo future và executor dùng bên trong nếu cần |
| Resolver trả `Mono<T>` nhưng gọi JDBC đồng bộ trong lambda | Cô lập phần blocking hoặc đổi sang reactive client; không dựa vào auto offload của controller |

## 10. Executor không làm tăng năng lực của database

Tăng số thread giúp ứng dụng có thể chờ nhiều I/O đồng thời hơn, nhưng không tự làm database xử lý nhanh hơn. Nếu pool có 100 tác vụ đồng thời trong khi connection pool chỉ có 10 kết nối, nhiều tác vụ vẫn phải chờ lấy connection.

Khi chọn executor, cần cân nhắc:

- Kích thước connection pool của database.
- Giới hạn đồng thời của HTTP client và dịch vụ downstream.
- Thời gian trung bình và p95/p99 của các lời gọi blocking.
- Số lượng GraphQL request đồng thời và số field resolver có thể được thực thi trong một operation.
- Queue capacity và chính sách từ chối task khi quá tải.
- Timeout của GraphQL request và timeout ở từng downstream.

Thread pool có queue không giới hạn có thể tích lũy lượng công việc lớn khi downstream chậm. Queue có giới hạn giúp áp lực được phản ánh sớm hơn, nhưng khi đầy, việc submit task có thể bị từ chối và cần xử lý như một lỗi thực thi. Không đặt `maxPoolSize` lớn hơn nhiều so với khả năng chịu tải của các tài nguyên phía sau mà không có số liệu đo.

## 11. Virtual threads: lợi ích và giới hạn

Virtual threads phù hợp với mô hình thread-per-request/task khi nhiều công việc chủ yếu chờ I/O blocking. Chúng giảm chi phí tạo và giữ thread so với platform thread, giúp code imperative tiếp tục dễ đọc.

Virtual threads không làm cho CPU-bound work chạy nhanh hơn. Chúng cũng không tăng giới hạn kết nối database, số request mà dịch vụ downstream chấp nhận hoặc thông lượng mạng. Nếu mỗi request tiêu thụ một connection trong thời gian dài, connection pool vẫn là giới hạn.

Một số điểm cần quan sát:

1. Dùng Java 21+; Java 24+ được khuyến nghị cho trải nghiệm virtual threads tốt hơn theo tài liệu Spring Boot hiện hành.
2. Kiểm tra pinned virtual threads khi ứng dụng có synchronized block hoặc native call giữ carrier thread lâu.
3. Đo connection pool, downstream concurrency và thời gian chờ, không chỉ đo số lượng thread.
4. Khi bật virtual threads, các thuộc tính cấu hình kích thước thread pool không còn tác dụng với executor virtual-thread được Boot tự cấu hình.
5. Virtual threads thường là daemon threads; ứng dụng phụ thuộc tác vụ nền cần kiểm tra vòng đời JVM và cấu hình keep-alive phù hợp.

## 12. Thread-local context và transaction boundary

Khi controller được gọi qua executor, method có thể chạy trên thread khác với thread xử lý transport. Không nên giả định mọi `ThreadLocal` từ thread ban đầu tự động xuất hiện trên worker thread.

Với dữ liệu phục vụ GraphQL như principal, tenant hoặc correlation ID, ưu tiên truyền qua `GraphQLContext`, method argument được Spring for GraphQL hỗ trợ hoặc cơ chế context propagation phù hợp. Nếu ứng dụng dựa vào Spring Security `SecurityContextHolder` hoặc thread-local tùy chỉnh, cần kiểm tra cấu hình executor và cơ chế truyền context tương ứng.

Transaction cũng gắn với thread trong các transaction manager imperative thông dụng. Nếu một transaction được mở ở thread request rồi controller method được offload, transaction đó không tự động chuyển sang worker thread. Đặt transaction boundary tại service được gọi trong worker thread hoặc dùng mô hình transaction phù hợp với execution model. Không giả định transaction mở ở một resolver cha sẽ bao trùm các resolver con chạy đồng thời trên các thread khác nhau.

## 13. Xử lý exception từ blocking controller

Exception phát sinh trong controller invocation hoặc bên trong `Callable` sẽ được đưa vào luồng xử lý lỗi của GraphQL. Có thể dùng `@GraphQlExceptionHandler` trong controller hoặc `@ControllerAdvice` để chuyển exception thành lỗi GraphQL có mã và thông điệp phù hợp.

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment
    ) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.NOT_FOUND)
                .message("Book was not found")
                .build();
    }
}
~~~

Không đưa chi tiết database, connection string hoặc stack trace vào message trả cho client. Log exception ở server với correlation ID để hỗ trợ điều tra. Việc chạy method trên executor không thay đổi nguyên tắc thiết kế lỗi GraphQL.

## 14. Kiểm thử executor được sử dụng

Với Spring Boot và Java 21+, có thể bật virtual threads trong test rồi xác nhận resolver đang chạy trên virtual thread. Ví dụ:

~~~java
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ThreadInfoController {

    @QueryMapping
    public boolean virtualThread() {
        return Thread.currentThread().isVirtual();
    }
}
~~~

SDL:

~~~graphql
type Query {
    virtualThread: Boolean!
}
~~~

Integration test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.threads.virtual.enabled=true"
)
@AutoConfigureHttpGraphQlTester
class BlockingControllerExecutorTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Test
    void invokesBlockingControllerOnVirtualThread() {
        graphQlTester.document("{ virtualThread }")
                .execute()
                .path("virtualThread")
                .entity(Boolean.class)
                .isEqualTo(true);
    }
}
~~~

Test này yêu cầu Java 21+, Spring Boot có hỗ trợ virtual threads và Spring for GraphQL 1.3+ có automatic blocking invocation. Với Spring Boot 3.x, thêm `org.springframework.graphql:spring-graphql-test`; nếu dùng `HttpGraphQlTester` qua WebTestClient và chưa có transport test trên classpath, thêm `org.springframework.boot:spring-boot-starter-webflux` ở test scope. Import `AutoConfigureHttpGraphQlTester` từ `org.springframework.boot.test.autoconfigure.graphql.tester`. Với Spring Boot 4.x, dùng `spring-boot-starter-graphql-test` và package `org.springframework.boot.graphql.test.autoconfigure.tester`. Với môi trường không dùng virtual threads, nên kiểm tra thread name hoặc thread identity theo executor tùy chỉnh thay vì gọi `Thread.isVirtual()`.

Ngoài ra nên có test cho:

1. `Callable<T>` thực thi trên executor đã cấu hình.
2. Method reactive `Mono`/`Flux` không bị đánh dấu blocking theo predicate mặc định.
3. Exception từ blocking method được chuyển thành GraphQL error đúng cách.
4. Executor queue đầy hoặc task bị từ chối có hành vi lỗi quan sát được.
5. Context cần thiết như principal/tenant vẫn có sẵn trong resolver.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Callable` không được đăng ký hoặc chạy | `AnnotatedControllerConfigurer` chưa có executor | Cấu hình `setExecutor` hoặc dùng Spring Boot executor phù hợp |
| Method trả `Book` vẫn chạy đồng bộ | Java dưới 21 hoặc Spring for GraphQL dưới 1.3, hay không có executor | Kiểm tra Java, Spring GraphQL và executor bean |
| Bật virtual threads nhưng method vẫn không offload | Property không được áp dụng, Boot starter không cấu hình configurer hoặc return type được xem là async | Kiểm tra effective properties, dependency version và method signature |
| Reactive method bị block | Blocking call nằm bên trong pipeline `Mono`/`Flux` | Dùng reactive client hoặc cô lập đoạn blocking bằng scheduler phù hợp |
| Database chậm dù có nhiều virtual threads | Connection pool hoặc database là giới hạn | Đo pool wait, query time và giới hạn concurrency |
| Request timeout khi queue dài | Task chờ executor hoặc downstream quá lâu | Giới hạn queue, đặt timeout và quan sát rejection |
| Mất SecurityContext/ThreadLocal | Method chạy trên thread khác | Truyền context rõ ràng hoặc cấu hình context propagation |
| Transaction không bao trùm resolver khác | Transaction gắn với thread và resolver có thể chạy đồng thời | Đặt transaction boundary tại service phù hợp; không dựa vào transaction của thread khác |

## 16. Quy trình lựa chọn Executor cho controller

Khi có controller dùng API blocking:

1. Xác định method nào thật sự gọi JDBC/JPA, blocking HTTP client hoặc I/O đồng bộ.
2. Nếu có thể, ưu tiên reactive client và reactive return type cho luồng reactive.
3. Nếu dùng Java 21+ và Spring for GraphQL 1.3+, cấu hình executor để automatic blocking invocation có thể offload method trả về `T`.
4. Với Spring Boot, cân nhắc `spring.threads.virtual.enabled=true` nếu workload phù hợp với virtual threads.
5. Nếu cần thread pool giới hạn, cấu hình `applicationTaskExecutor` và đo pool/queue theo tài nguyên downstream.
6. Với Java thấp hơn 21 hoặc muốn chọn rõ phần công việc bất đồng bộ, dùng `Callable<T>` cùng executor.
7. Chỉ thay thế `AnnotatedControllerConfigurer` khi cần kiểm soát trực tiếp; giữ lại các custom resolver và exception handling cần thiết.
8. Kiểm thử thread thực thi, lỗi, context propagation, timeout và áp lực lên database.

Executor giúp cô lập các lời gọi blocking khỏi thread xử lý request và cho phép GraphQL tiếp tục điều phối kết quả bất đồng bộ. Hiệu quả thực tế phụ thuộc vào cách chọn executor, khả năng của database/downstream và việc phân biệt đúng controller blocking với reactive controller.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution and Thread Model](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL 1.4 — AnnotatedControllerConfigurer API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/method/annotation/support/AnnotatedControllerConfigurer.html)
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [Spring Boot — Virtual Threads](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.virtual-threads)
