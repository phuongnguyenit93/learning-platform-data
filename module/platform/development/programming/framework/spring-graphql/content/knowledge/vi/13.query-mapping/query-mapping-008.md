# Query blocking trong Spring for GraphQL

Trong Spring for GraphQL, một phương thức `@QueryMapping` có thể trả về object trực tiếp sau khi gọi repository hoặc service. Cách viết này đơn giản, nhưng nếu thao tác bên trong dùng API đồng bộ như JDBC, JPA hoặc `RestTemplate`, lời gọi sẽ **chặn thread hiện tại** cho tới khi I/O hoàn tất.

Blocking không phải đặc tính bắt buộc của GraphQL Query. Nó xuất phát từ cách DataFetcher thực hiện công việc. Khi ứng dụng dùng Spring MVC, xử lý đồng bộ thường chạy trên servlet request thread. Khi dùng Spring WebFlux, blocking I/O trên event-loop có thể làm chậm nhiều request khác. Vì vậy cần hiểu web stack, loại I/O và cách tổ chức executor trước khi chọn cách triển khai Query.

## Một Query blocking trông như thế nào?

Giả sử schema có field tra cứu sản phẩm:

```graphql
type Product {
  id: ID!
  name: String!
  price: Float!
}

type Query {
  product(id: ID!): Product
}
```

Controller có thể viết rất ngắn:

```java
@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public Product product(@Argument String id) {
        return productService.findById(id).orElse(null);
    }
}
```

Đoạn code trên là một synchronous DataFetcher. Nếu `findById` gọi Spring Data JPA repository, thread thực thi phải chờ database trả kết quả trước khi phương thức hoàn tất. Nếu database mất 300 ms, thread đó bị giữ trong khoảng thời gian chờ tương ứng, chưa kể thời gian xử lý còn lại.

`@QueryMapping` chỉ ánh xạ phương thức tới field của Query root. Annotation không tự biến lời gọi đồng bộ thành bất đồng bộ và cũng không tự chuyển công việc sang thread pool khác.

## Blocking ảnh hưởng thế nào trong MVC và WebFlux?

### Với Spring MVC

Trong mô hình servlet truyền thống, mỗi request thường được xử lý trên một servlet thread. Khi DataFetcher gọi JPA/JDBC đồng bộ, thread request chờ I/O rồi tiếp tục tạo GraphQL response.

Cách này có thể phù hợp nếu:

- Ứng dụng đang dùng Spring MVC và thư viện truy cập dữ liệu đồng bộ.
- Thời gian truy vấn được kiểm soát và connection pool/database có giới hạn phù hợp.
- Số request đồng thời nằm trong khả năng của servlet thread pool.
- Có timeout và giám sát để phát hiện truy vấn chậm.

Dù chấp nhận blocking, một lượng lớn request chờ database vẫn có thể giữ hết servlet threads, làm request mới phải xếp hàng hoặc bị từ chối. Cần giới hạn concurrency và tối ưu truy vấn thay vì chỉ tăng số thread.

### Với Spring WebFlux

WebFlux thường chạy trên event-loop có số thread nhỏ. Một event-loop thread có thể phục vụ nhiều kết nối. Nếu một DataFetcher gọi JDBC/JPA đồng bộ trực tiếp trên thread này, nó giữ event loop trong lúc chờ I/O. Những request khác được giao cho cùng event loop cũng có thể bị trì hoãn.

Với WebFlux, nên ưu tiên client và driver non-blocking như WebClient hoặc R2DBC. Nếu buộc phải dùng thư viện blocking, hãy offload công việc sang executor hoặc scheduler dành riêng cho blocking I/O.

| Mô hình | Khi DataFetcher gọi JDBC/JPA đồng bộ |
| --- | --- |
| Spring MVC | Chặn servlet request thread cho tới khi I/O hoàn tất. Có thể chấp nhận nếu giới hạn thread, connection và timeout hợp lý. |
| Spring WebFlux | Có nguy cơ chặn event-loop và làm giảm khả năng phục vụ nhiều request. Cần chuyển blocking I/O sang worker thread. |

GraphQL Java có thể điều phối các field và phối hợp kết quả bất đồng bộ, nhưng điều đó không có nghĩa một lời gọi DataFetcher đồng bộ tự động được offload. Nếu code gọi repository trước khi trả về kết quả, thread hiện tại vẫn bị chặn.

## Offload blocking I/O bằng CompletableFuture

Một cách rõ ràng là trả về `CompletableFuture` và chạy lời gọi blocking trên một executor được quản lý. Ví dụ tạo executor riêng cho GraphQL blocking I/O:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class GraphQlExecutorConfiguration {

    @Bean("graphqlBlockingExecutor")
    ThreadPoolTaskExecutor graphqlBlockingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("graphql-blocking-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
```

Các con số chỉ là giá trị minh họa. Khi triển khai, cần chọn pool size và queue capacity dựa trên số kết nối database, giới hạn của dịch vụ phụ thuộc, số request đồng thời và thời gian I/O. Không nên tăng max pool tùy tiện vì số thread lớn có thể làm database hoặc dịch vụ downstream quá tải.

Controller inject executor và trả về future:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ProductController {

    private final ProductService productService;
    private final Executor graphqlBlockingExecutor;

    public ProductController(
            ProductService productService,
            @Qualifier("graphqlBlockingExecutor") Executor graphqlBlockingExecutor) {
        this.productService = productService;
        this.graphqlBlockingExecutor = graphqlBlockingExecutor;
    }

    @QueryMapping
    public CompletableFuture<Product> product(@Argument String id) {
        return CompletableFuture.supplyAsync(
                () -> productService.findById(id).orElse(null),
                graphqlBlockingExecutor);
    }
}
```

Ở đây lời gọi `productService.findById` chỉ bắt đầu bên trong supplier được executor chạy. GraphQL nhận `CompletableFuture` và hoàn tất field khi future hoàn thành. Request không cần giữ thread hiện tại để chờ chính lời gọi blocking đó.

Executor có hàng đợi hữu hạn để tránh giữ số lượng task không giới hạn. Cần xác định hành vi khi queue đầy, theo dõi số task chờ, thời gian chờ và số lần từ chối. Một pool riêng cũng giúp cô lập blocking I/O của GraphQL khỏi các công việc khác trong ứng dụng.

## Offload bằng Reactor khi ứng dụng dùng WebFlux

Với controller reactive, có thể bọc lời gọi blocking bằng `Mono.fromCallable` rồi chuyển nó sang `Schedulers.boundedElastic()`:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public Mono<Product> product(@Argument String id) {
        return Mono.fromCallable(
                    () -> productService.findById(id).orElse(null))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
```

`fromCallable` trì hoãn lời gọi tới khi có subscription. `subscribeOn(boundedElastic())` chuyển việc thực thi callable sang scheduler phù hợp cho blocking work. Đây là cách chuyển tiếp hữu ích khi chưa thể thay JDBC/JPA bằng driver non-blocking.

Không viết như sau:

```java
@QueryMapping
public Mono<Product> product(@Argument String id) {
    Product product = productService.findById(id).orElse(null);
    return Mono.just(product);
}
```

Trong ví dụ sai này, repository đã được gọi đồng bộ trước khi `Mono.just` được tạo. Việc trả `Mono` không làm cho đoạn truy cập dữ liệu trở thành non-blocking.

`boundedElastic` dành cho công việc blocking có giới hạn, không phải lựa chọn mặc định cho mọi tác vụ. Nếu đã dùng WebClient hoặc R2DBC với API non-blocking, hãy trả trực tiếp `Mono`/`Flux` từ các API đó thay vì chuyển sang boundedElastic không cần thiết.

## Chọn giữa synchronous, CompletableFuture và Mono

| Cách triển khai | Phù hợp khi | Điểm cần lưu ý |
| --- | --- | --- |
| Trả object trực tiếp | Ứng dụng MVC dùng JPA/JDBC đồng bộ và tải được kiểm soát. | Thread request chờ I/O; phải theo dõi thread pool và connection pool. |
| `CompletableFuture` với executor | Muốn offload blocking I/O sang pool riêng hoặc tích hợp API trả future. | Dùng executor có giới hạn; xử lý lỗi và context truyền sang thread khác. |
| `Mono.fromCallable(...).subscribeOn(boundedElastic())` | Ứng dụng reactive cần tạm dùng thư viện blocking. | Callable phải chứa lời gọi blocking; cần giới hạn và giám sát scheduler. |
| `Mono`/`Flux` từ API non-blocking | Dùng WebClient, R2DBC hoặc nguồn reactive thực sự. | Giữ pipeline non-blocking xuyên suốt, không gọi blocking API giữa pipeline. |

Không có một kiểu trả về tốt nhất cho mọi dự án. Hãy chọn dựa trên web stack và API của tầng dữ liệu. Một ứng dụng Spring MVC có JPA không cần chuyển mọi controller sang Reactor chỉ để có vẻ bất đồng bộ. Một ứng dụng WebFlux không nên gọi JDBC trực tiếp trên event loop.

## Đừng nhầm async với tăng tốc truy vấn

Offload một blocking query giúp giải phóng thread đang nhận request, nhưng không làm database xử lý truy vấn nhanh hơn. Nếu câu SQL mất 2 giây, task vẫn tiêu tốn connection và tài nguyên database trong khoảng thời gian đó.

Trước khi tăng concurrency, hãy kiểm tra:

- Query plan, index và số hàng thực tế được đọc.
- Connection pool có đủ cho concurrency dự kiến hay không.
- Có gọi nhiều service hoặc repository dư thừa trong cùng một operation không.
- Có thể phân trang hoặc giới hạn số lượng dữ liệu trả về không.
- Có thể batch các field quan hệ để tránh N+1 không.
- Downstream có timeout và giới hạn rate phù hợp không.

Ví dụ một Query trả danh sách Product rồi resolve seller cho từng Product có thể tạo N+1. Offload từng lời gọi seller sang executor chỉ làm nhiều truy vấn chạy đồng thời; nó không loại bỏ số truy vấn dư thừa. Dùng DataLoader hoặc `@BatchMapping` để gom các key thường hiệu quả hơn.

## Kiểm soát thread pool và tải đồng thời

Khi offload blocking work, executor trở thành một tài nguyên cần vận hành. Cần quan tâm:

1. **Pool size:** nên cân bằng với connection pool và giới hạn dịch vụ downstream. Nếu executor có 32 thread nhưng database chỉ có 10 connection, phần còn lại có thể chỉ chờ connection.
2. **Queue capacity:** queue hữu hạn giúp tạo backpressure ở tầng ứng dụng. Queue quá lớn làm tăng độ trễ và giữ nhiều request lâu hơn.
3. **Rejection policy:** khi pool và queue đều đầy, cần hành vi từ chối rõ ràng và ánh xạ thành lỗi phù hợp thay vì tạo thêm thread vô hạn.
4. **Timeout:** cấu hình timeout cho database statement, HTTP client và các dịch vụ phụ thuộc. Timeout ở tầng client không nhất thiết dừng được lời gọi JDBC đang chạy.
5. **Shutdown:** cho executor thời gian hoàn tất các task đang chạy và theo dõi task bị gián đoạn khi ứng dụng dừng.
6. **Metrics:** theo dõi active threads, queue size, rejected tasks, thời gian chờ và thời gian chạy.

Đừng tạo một executor mới cho mỗi request hoặc mỗi lần gọi resolver. Hãy dùng bean được quản lý bởi Spring và có giới hạn rõ ràng.

## Transaction và context khi chuyển thread

Chuyển blocking work sang thread khác có thể ảnh hưởng tới các thông tin gắn với thread hiện tại.

### Transaction

Các transaction JDBC/JPA của Spring thường gắn với thread. Nếu controller mở transaction rồi tạo `CompletableFuture` trên executor khác, transaction của thread ban đầu không tự động đi theo task bất đồng bộ.

Với công việc cần transaction, nên gọi một phương thức service có `@Transactional` bên trong supplier để transaction được mở trên worker thread:

```java
@Service
public class ProductService {

    @Transactional(readOnly = true)
    public Product findProduct(String id) {
        return productRepository.findById(id).orElse(null);
    }
}
```

```java
@QueryMapping
public CompletableFuture<Product> product(@Argument String id) {
    return CompletableFuture.supplyAsync(
            () -> productService.findProduct(id),
            graphqlBlockingExecutor);
}
```

Trong ví dụ này, lời gọi qua Spring service proxy diễn ra trên worker thread nên transaction được áp dụng cho thread thực thi đó. Không giả định transaction của request thread bao phủ phần việc đã chuyển sang executor.

### Security context, tenant và MDC

Các dữ liệu như `SecurityContextHolder`, MDC hoặc request-scoped state có thể được lưu trong ThreadLocal. Khi chuyển thread, chúng không tự động được sao chép trong mọi cấu hình.

- Nếu công việc cần danh tính, có thể lấy principal đã xác thực trong controller rồi truyền một giá trị định danh bất biến vào service.
- Nếu code phụ thuộc `SecurityContextHolder`, dùng executor có khả năng truyền `SecurityContext` như `DelegatingSecurityContextExecutor` hoặc cấu hình `TaskDecorator` phù hợp.
- Nếu cần correlation ID trong log, cấu hình `TaskDecorator` để sao chép và khôi phục MDC, đồng thời dọn ThreadLocal sau khi task kết thúc.
- Không truyền `HttpServletRequest`, response hoặc object request-scoped qua các task có thể chạy sau vòng đời request.

Với dữ liệu tenant, luôn xác minh tenant ở server và truyền phạm vi đã xác thực tới service. Không dùng tenant ID do client tự gửi như nguồn quyền hạn.

## Cancellation và lỗi

Client có thể ngắt kết nối trước khi blocking task hoàn tất. Việc hủy một `CompletableFuture` không bảo đảm lời gọi JDBC hoặc thư viện blocking bên dưới dừng ngay. Vì vậy, cần timeout ở chính database driver, HTTP client hoặc dịch vụ đang được gọi.

Với Reactor, cancellation được truyền qua pipeline, nhưng một lời gọi blocking đang chạy cũng không phải lúc nào có thể dừng an toàn. Dùng timeout và API có khả năng hủy nếu thư viện hỗ trợ; không dựa riêng vào việc client đóng kết nối.

Lỗi từ `CompletableFuture` hoặc `Mono` sẽ trở thành execution error của field. Spring for GraphQL hỗ trợ `DataFetcherExceptionResolver` để ánh xạ exception sang message và error code công khai. Không trả stack trace, SQL hoặc thông tin hạ tầng cho client.

Nếu field được khai báo nullable, lỗi có thể khiến field đó trở thành `null` trong khi các field khác vẫn trả dữ liệu. Nếu field là Non-Null, null có thể lan lên field cha theo quy tắc GraphQL. Thiết kế nullability và error handling cần thống nhất với hợp đồng API.

## Kiểm thử Query blocking

Kiểm thử nên xác minh kết quả GraphQL và cách ứng dụng xử lý blocking work:

- Query trả đúng dữ liệu khi repository có kết quả.
- Trường hợp không tìm thấy tuân theo nullability và quy ước lỗi.
- Blocking call được chạy trên executor/scheduler dự kiến trong cấu hình WebFlux.
- Executor có giới hạn và hành vi khi queue đầy được xử lý phù hợp.
- Exception từ service được ánh xạ thành GraphQL error có thể xử lý.
- Transaction được mở trong thread thực thi nếu service cần transaction.
- Principal, tenant và correlation ID được truyền đúng khi task chạy bất đồng bộ.
- Timeout và cancellation không làm giữ tài nguyên vô hạn.
- Các field quan hệ không tạo N+1 khi query danh sách lớn.

Ví dụ kiểm tra kết quả bằng `GraphQlTester`:

```java
@Test
void productQueryReturnsProduct() {
    graphQlTester.document("""
        query {
          product(id: "p-100") {
            id
            name
          }
        }
        """)
        .execute()
        .path("product.id")
        .entity(String.class)
        .isEqualTo("p-100");
}
```

Để kiểm tra offload, có thể cho service ghi nhận tên thread trong test hoặc dùng một executor test có thể quan sát. Không nên chỉ đo thời gian chạy một test đơn lẻ để kết luận hệ thống non-blocking; cần kiểm tra thread thực thi và tải đồng thời trong môi trường gần với production.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| WebFlux chậm khi database có độ trễ | JDBC/JPA chạy trực tiếp trên event-loop. | Dùng R2DBC hoặc offload blocking call sang worker scheduler/executor. |
| Trả `Mono` nhưng thread vẫn bị chặn | Blocking call chạy trước `Mono.just`. | Đưa lời gọi vào `Mono.fromCallable` và dùng `subscribeOn`. |
| Tạo nhiều thread nhưng throughput không tăng | Database connection pool hoặc downstream đã bão hòa. | Giới hạn concurrency, kiểm tra pool và tối ưu query. |
| Transaction không bao phủ async task | Transaction được mở trên thread khác. | Gọi service `@Transactional` bên trong task trên executor. |
| Log thiếu correlation ID hoặc mất principal | ThreadLocal context không được truyền sang worker. | Truyền context tường minh hoặc cấu hình executor decorator. |
| Client timeout nhưng JDBC vẫn chạy | Hủy future không dừng được lời gọi blocking. | Cấu hình timeout ở driver và downstream, giới hạn thời gian truy vấn. |
| Query danh sách vẫn tạo nhiều SQL | Offload từng resolver nhưng chưa batch dữ liệu quan hệ. | Dùng DataLoader hoặc `@BatchMapping`. |

## Ghi nhớ

Query blocking thường xuất hiện khi `@QueryMapping` gọi API đồng bộ như JDBC, JPA hoặc HTTP client blocking. Trong Spring MVC, công việc đó chặn servlet thread; trong Spring WebFlux, chặn event-loop có thể ảnh hưởng nhiều request khác. Annotation `@QueryMapping` và GraphQL async execution không tự offload lời gọi blocking.

Với MVC và JPA, synchronous handler có thể phù hợp nếu giới hạn tải, thread và connection được kiểm soát. Với WebFlux, ưu tiên API non-blocking; nếu phải dùng thư viện blocking, chuyển lời gọi sang executor có giới hạn hoặc `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`. Cần quản lý transaction, security context, timeout, cancellation và N+1 cùng với thread pool để Query hoạt động ổn định.
