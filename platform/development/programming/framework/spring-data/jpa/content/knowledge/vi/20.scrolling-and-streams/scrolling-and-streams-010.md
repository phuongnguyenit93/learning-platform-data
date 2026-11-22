# Truy vấn bất đồng bộ với @Async và giới hạn của JPA đồng bộ

## 1. Vì sao cần chạy truy vấn bất đồng bộ?

Một endpoint có thể phải đọc dữ liệu mất nhiều thời gian: tìm kiếm với nhiều điều kiện, tổng hợp báo cáo, kiểm tra trạng thái đơn hàng hoặc tải dữ liệu cho một tác vụ nền. Nếu controller gọi repository đồng bộ, thread đang xử lý HTTP request sẽ chờ cho tới khi JDBC và database hoàn tất truy vấn.

Spring Framework cung cấp `@Async` để thực thi một method trên task executor. Spring Data JPA có thể kết hợp `@Async` với query method trả về `Future` hoặc `CompletableFuture`. Điều này giúp thread gọi không phải trực tiếp chờ method hoàn tất.

Tuy nhiên, cần hiểu giới hạn quan trọng: **JPA và JDBC vẫn là API đồng bộ, blocking**. Khi query chạy trên executor thread, thread đó vẫn chờ database trả kết quả. `@Async` chuyển công việc sang thread khác và cho phép xử lý nhiều tác vụ đồng thời; nó không biến JDBC thành non-blocking I/O và không tự làm một câu SQL chạy nhanh hơn.

Ba khái niệm cần phân biệt:

- **Đồng bộ:** caller gọi method và chờ kết quả ngay trên cùng luồng thực thi.
- **Bất đồng bộ với @Async:** Spring gửi lời gọi tới executor; caller nhận một Future và có thể tiếp tục làm việc trong khi worker thread chạy query blocking.
- **Reactive/non-blocking:** luồng xử lý không giữ một thread chờ I/O; cần driver và data access stack hỗ trợ non-blocking từ đầu đến cuối.

Spring Data JPA phù hợp với mô hình imperative/blocking. Nếu cần reactive database access thực sự, hãy xem xét Spring Data R2DBC và database driver tương ứng.

## 2. @Async hoạt động như thế nào?

### 2.1. Cơ chế proxy và TaskExecutor

Khi bật async support, Spring tạo proxy cho bean có method được đánh dấu `@Async`. Khi một bean khác gọi method qua proxy:

1. Proxy nhận lời gọi và xác định executor sẽ dùng.
2. Công việc được gửi tới executor dưới dạng task.
3. Executor chọn một worker thread để thực thi method.
4. Caller nhận về Future/CompletableFuture thay vì chờ kết quả trực tiếp.
5. Khi method hoàn tất, Future được hoàn thành bằng kết quả hoặc exception.

Luồng khái quát:

```text
HTTP request thread
       |
       | gọi method qua Spring proxy
       v
   @Async proxy
       |
       | submit task
       v
  TaskExecutor queue
       |
       v
  Worker thread
       |
       | gọi repository / JDBC
       v
    Database
       |
       | kết quả
       v
 CompletableFuture hoàn tất
       |
       v
 Spring MVC / caller tiếp tục xử lý
```

Worker thread vẫn bị chiếm dụng trong lúc JDBC chờ database. Lợi ích là thread gọi được giải phóng hoặc có thể tiếp tục công việc khác, còn query chạy độc lập trong executor.

### 2.2. Bật async support

Cần khai báo `@EnableAsync` trong cấu hình Spring:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
```

Import:

```java
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.context.annotation.Configuration;
```

Chỉ thêm annotation `@Async` mà không bật async support thì method có thể vẫn được gọi đồng bộ như một method Java thông thường.

### 2.3. @Async dựa trên Spring proxy

Lời gọi phải đi qua proxy của Spring. Ví dụ sau không kích hoạt async:

```java
@Service
public class ReportService {

    public CompletableFuture<Report> generate() {
        return generateAsync(); // self-invocation
    }

    @Async
    public CompletableFuture<Report> generateAsync() {
        // Công việc nặng
        return CompletableFuture.completedFuture(new Report());
    }
}
```

`generateAsync()` được gọi trực tiếp từ cùng instance qua `this`, không đi qua proxy, nên interceptor `@Async` không được áp dụng.

Cách tổ chức tốt hơn là đặt method async ở một Spring bean riêng rồi gọi bean đó từ service khác. Tránh dùng self-injection hoặc lấy proxy thủ công chỉ để né self-invocation nếu có thể tách trách nhiệm rõ ràng.

Các method async nên là method public được gọi từ bean khác. Nếu dùng class-based proxy, class/method final có thể cản trở proxy subclass; hãy tuân thủ kiểu proxy mà ứng dụng đang cấu hình.

## 3. Cấu hình ThreadPoolTaskExecutor

### 3.1. Vì sao nên dùng executor riêng?

Nếu không chỉ định executor, Spring có thể chọn executor mặc định theo cấu hình ứng dụng. Với query JPA, nên đặt tên executor riêng để kiểm soát số worker thread và giới hạn hàng đợi.

Ví dụ cấu hình:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean(name = "jpaQueryExecutor")
    public ThreadPoolTaskExecutor jpaQueryExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("jpa-query-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);

        return executor;
    }
}
```

Spring quản lý vòng đời bean và khởi tạo ThreadPoolTaskExecutor. Các con số trong ví dụ chỉ là điểm bắt đầu minh họa, không phải cấu hình tối ưu cho mọi ứng dụng.

### 3.2. Ý nghĩa các tham số

| Thuộc tính | Ý nghĩa |
|---|---|
| corePoolSize | Số worker thread cốt lõi được giữ trong pool |
| maxPoolSize | Số worker tối đa khi tải tăng |
| queueCapacity | Số task tối đa chờ trong queue |
| threadNamePrefix | Prefix giúp nhận diện worker trong thread dump và log |
| waitForTasksToCompleteOnShutdown | Cho phép task đang chờ/đang chạy hoàn tất khi shutdown theo chính sách executor |
| awaitTerminationSeconds | Thời gian chờ executor kết thúc khi shutdown |

Queue không nên vô hạn. Nếu database chậm nhưng ứng dụng tiếp tục nhận task, queue vô hạn có thể tích lũy rất nhiều request, giữ dữ liệu trong heap và làm tăng độ trễ. Queue có giới hạn giúp hệ thống có điểm kiểm soát áp lực.

Khi pool và queue đã đầy, executor có thể từ chối task. Ứng dụng cần xác định cách phản hồi, retry hoặc đưa công việc vào hàng đợi bền vững. Không nên âm thầm bỏ task quan trọng.

### 3.3. Kích thước executor phải phù hợp connection pool

Mỗi query JPA cần connection database khi thực thi SQL. Nếu có 50 worker thread nhưng connection pool chỉ cho phép 10 connection, nhiều worker sẽ chờ connection; chúng vẫn chiếm thread dù chưa chạy SQL.

Ngược lại, tăng connection pool quá lớn có thể làm database quá tải. Cần cân nhắc đồng thời:

- Số request async đồng thời.
- Kích thước connection pool (ví dụ HikariCP).
- Giới hạn kết nối mà database cho phép.
- Thời gian query trung bình và p95/p99.
- CPU, I/O và khả năng xử lý của database.
- Tài nguyên dành cho request đồng bộ và các job khác.

Không có công thức cố định như maxPoolSize phải luôn bằng connection pool. Hãy đo tải thực tế, dành connection cho các luồng quan trọng khác và đặt giới hạn concurrency phù hợp.

## 4. Truy vấn repository bằng @Async

### 4.1. Khai báo async query method

Giả sử cần tìm khách hàng theo trạng thái và trả DTO:

```java
public record CustomerSummary(Long id, String name) {
}
```

Repository:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Async("jpaQueryExecutor")
    @Transactional(readOnly = true)
    @Query("""
        select new com.example.customer.dto.CustomerSummary(
            c.id,
            c.name
        )
        from Customer c
        where c.status = :status
        order by c.name, c.id
        """)
    CompletableFuture<List<CustomerSummary>> findSummariesAsync(
        @Param("status") CustomerStatus status
    );
}
```

Các điểm cần chú ý:

- `@Async("jpaQueryExecutor")` chọn executor có tên đã cấu hình.
- Query method trả `CompletableFuture<List<CustomerSummary>>`, không trả trực tiếp List nếu muốn dùng async query execution.
- `@Transactional(readOnly = true)` chỉ rõ query cần chạy trong transaction đọc.
- JPQL constructor expression tạo DTO, tránh trả entity có quan hệ lazy cho caller ở thread khác.
- `ORDER BY` có ID làm tie-breaker để thứ tự kết quả xác định hơn.

Spring Data JPA hỗ trợ async query method với các kiểu Future phù hợp. Cú pháp và một số khả năng cụ thể phụ thuộc phiên bản Spring Data. Kiểm tra dependency của dự án nếu dùng kiểu trả về đặc biệt hoặc kết hợp paging/projection phức tạp.

### 4.2. Vì sao cần transaction rõ ràng?

Các query method khai báo bằng tên hoặc `@Query` không nhất thiết nhận transaction configuration mặc định giống các phương thức CRUD kế thừa. Hãy khai báo `@Transactional` ở method hoặc tầng service phù hợp.

Transaction imperative của Spring gắn với thread thực thi. Khi `@Async` chuyển lời gọi sang worker thread, transaction đang mở ở caller thread không tự truyền sang worker thread.

Vì vậy, nếu query cần transaction, transaction phải được bắt đầu trên worker thread. Đặt transaction boundary ở async query method hoặc gọi một service worker riêng có `@Transactional(readOnly = true)` từ async thread.

### 4.3. Cách gọi và xử lý kết quả

Caller nhận CompletableFuture:

```java
CompletableFuture<List<CustomerSummary>> future =
    customerRepository.findSummariesAsync(CustomerStatus.ACTIVE);

future.thenAccept(customers -> {
    // Xử lý kết quả khi hoàn tất
});
```

Không gọi `get()` hoặc `join()` ngay sau khi nhận future trong controller nếu mục tiêu là tránh chặn thread request. Làm như vậy khiến caller chờ lại và mất lợi ích của async.

Nếu cần chuyển đổi kết quả:

```java
CompletableFuture<CustomerPageResponse> response =
    customerRepository
        .findSummariesAsync(CustomerStatus.ACTIVE)
        .thenApply(CustomerPageResponse::from);
```

Các callback `thenApply`/ `thenAccept` không có hậu tố Async có thể chạy trên thread hoàn tất future. Nếu bước xử lý tiếp theo tốn CPU hoặc blocking, hãy cân nhắc executor riêng cho bước đó thay vì chiếm worker thread dành cho query JPA.

## 5. Async ở tầng service và transaction worker

Trong nhiều ứng dụng, đặt async ở service giúp tách API bất đồng bộ khỏi repository. Repository vẫn là API JPA đồng bộ; service gọi nó từ worker thread.

Ví dụ:

```java
@Service
public class CustomerAsyncService {

    private final CustomerQueryWorker queryWorker;

    public CustomerAsyncService(CustomerQueryWorker queryWorker) {
        this.queryWorker = queryWorker;
    }

    @Async("jpaQueryExecutor")
    public CompletableFuture<List<CustomerSummary>> searchAsync(
        String keyword
    ) {
        List<CustomerSummary> result =
            queryWorker.search(keyword);

        return CompletableFuture.completedFuture(result);
    }
}
```

Worker có transaction riêng:

```java
@Service
public class CustomerQueryWorker {

    private final CustomerRepository repository;

    public CustomerQueryWorker(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<CustomerSummary> search(String keyword) {
        return repository.searchSummaries(keyword);
    }
}
```

Repository method ở ví dụ này là query đồng bộ thông thường:

```java
@Query("""
    select new com.example.customer.dto.CustomerSummary(
        c.id,
        c.name
    )
    from Customer c
    where lower(c.name) like lower(concat('%', :keyword, '%'))
    order by c.name, c.id
    """)
List<CustomerSummary> searchSummaries(
    @Param("keyword") String keyword
);
```

Cách tách bean bảo đảm lời gọi `queryWorker.search()` đi qua transaction proxy. Transaction được mở trên worker thread vì lời gọi diễn ra bên trong method async. `CompletableFuture.completedFuture()` bọc kết quả đã được tính trong worker; không cần tạo thêm một executor thứ hai.

Chọn một trong hai cách:
- Async trực tiếp trên repository query method khi chỉ cần chạy một query độc lập.
- Async ở service và gọi worker/repository đồng bộ khi cần gom nhiều bước nghiệp vụ trong cùng transaction worker.

Không lồng nhiều `@Async` executor cho cùng một query nếu không có lý do rõ ràng.

## 6. Transaction không được kế thừa từ caller

### 6.1. Transaction gắn với thread

Trong mô hình imperative, Spring transaction manager thường giữ transaction resource và trạng thái transaction theo thread hiện tại. `@Transactional` ở caller thread không tự chuyển sang executor thread.

Ví dụ:

```java
@Transactional
public void createOrderAndStartReport() {
    orderRepository.save(newOrder);

    reportService.generateAsync();
}
```

Nếu `generateAsync()` chạy trên worker thread, nó không tự tham gia transaction của `createOrderAndStartReport()`. Worker cần transaction riêng nếu truy vấn/ghi dữ liệu yêu cầu transaction.

### 6.2. Async có thể chạy trước khi transaction caller commit

Một tình huống nguy hiểm:

1. Caller lưu một bản ghi mới trong transaction.
2. Caller gửi async task để đọc bản ghi đó.
3. Worker bắt đầu trước khi caller commit.
4. Worker dùng transaction riêng và có thể chưa nhìn thấy bản ghi mới.

Không giả định async task sẽ nhìn thấy dữ liệu chưa commit của caller. Nếu công việc phải chạy sau khi transaction gốc commit, dùng sự kiện sau commit như `@TransactionalEventListener(phase = AFTER_COMMIT)` hoặc transactional outbox cho tác vụ cần độ tin cậy cao.

Ví dụ sự kiện sau commit:

```java
public record OrderCreatedEvent(Long orderId) {
}
```

Phát sự kiện trong transaction:

```java
publisher.publishEvent(new OrderCreatedEvent(order.getId()));
```

Listener:

```java
@Component
public class OrderCreatedListener {

    private final ReportAsyncService reportAsyncService;

    public OrderCreatedListener(ReportAsyncService reportAsyncService) {
        this.reportAsyncService = reportAsyncService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        reportAsyncService.generateAsync(event.orderId());
    }
}
```

Listener chỉ được kích hoạt sau khi transaction commit thành công. Nếu cần bảo đảm event không bị mất khi process dừng giữa commit và publish, transactional outbox thường phù hợp hơn một event in-memory đơn thuần.

## 7. Không chia sẻ EntityManager hoặc managed entity giữa các thread

### 7.1. EntityManager không thread-safe

EntityManager và persistence context không được thiết kế để nhiều thread dùng đồng thời. Mỗi worker cần persistence context/transaction của chính nó do Spring quản lý.

Không truyền EntityManager từ request thread sang async thread. Không mở một EntityManager thủ công rồi chia sẻ nó cho nhiều task.

### 7.2. Managed entity có thể trở thành detached

Một repository query có thể trả entity được quản lý trong persistence context của transaction worker. Khi transaction kết thúc và persistence context đóng, entity không còn managed trong context đó.

Nếu caller nhận entity và truy cập quan hệ lazy sau khi transaction worker đã kết thúc, có thể gặp `LazyInitializationException` với Hibernate.

Vì vậy, nên:
- Trả DTO hoặc projection chứa đúng dữ liệu cần thiết.
- Fetch association cần dùng ngay trong transaction worker.
- Map entity thành DTO trước khi trả kết quả.
- Không gửi managed entity sang thread khác rồi kỳ vọng dirty checking tiếp tục hoạt động.

Ví dụ query trả DTO bằng constructor expression:

```java
@Query("""
    select new com.example.customer.dto.CustomerSummary(
        c.id,
        c.name
    )
    from Customer c
    where c.status = :status
    """)
List<CustomerSummary> findSummaries(
    @Param("status") CustomerStatus status
);
```

DTO chứa dữ liệu đã materialize, không phụ thuộc lazy proxy sau khi transaction đóng.

### 7.3. Không truyền association lazy chưa khởi tạo

Ngay cả khi entity được trả về dưới dạng Future, proxy lazy bên trong vẫn có thể chưa được khởi tạo. Chỉ gọi getter sau khi transaction đóng có thể gây lỗi. Nếu cần quan hệ, dùng fetch join, EntityGraph hoặc projection để lấy dữ liệu cần thiết trước khi kết thúc worker transaction.

## 8. CompletableFuture và xử lý lỗi

### 8.1. Trả exception qua Future

Nếu async method ném exception, CompletableFuture hoàn tất ở trạng thái exceptional. Caller có thể xử lý:

```java
CompletableFuture<List<CustomerSummary>> future =
    customerRepository.findSummariesAsync(CustomerStatus.ACTIVE);

future.exceptionally(error -> {
    // Ghi nhận lỗi và trả giá trị dự phòng phù hợp
    return List.of();
});
```

Không nên biến mọi lỗi thành danh sách rỗng nếu nghiệp vụ cần phân biệt “không có dữ liệu” với “database lỗi”. Hãy map lỗi sang kết quả hoặc HTTP response đúng hợp đồng API.

Dùng `handle()` nếu cần xử lý cả kết quả và exception:

```java
future.handle((result, error) -> {
    if (error != null) {
        throw new CompletionException(error);
    }

    return result;
});
```

### 8.2. Kết hợp nhiều tác vụ

Có thể chạy các query độc lập song song:

```java
CompletableFuture<List<CustomerSummary>> customers =
    customerRepository.findSummariesAsync(CustomerStatus.ACTIVE);

CompletableFuture<List<OrderSummary>> orders =
    orderRepository.findRecentSummariesAsync();

CompletableFuture<DashboardResponse> dashboard =
    customers.thenCombine(orders, DashboardResponse::new);
```

Hai query có thể chạy đồng thời trên executor, nhưng điều đó tăng số connection và tải database. Chỉ song song hóa khi các công việc độc lập và database còn đủ capacity.

Nếu các bước phụ thuộc kết quả nhau, dùng `thenCompose` để nối Future thay vì chặn thread bằng `get()` hoặc `join()`.

### 8.3. Timeout và cancellation

Caller có thể đặt timeout cho việc chờ kết quả bằng các API CompletableFuture hoặc timeout ở tầng HTTP. Tuy nhiên, timeout của caller không nhất thiết dừng câu SQL đang chạy trong database.

Cần phân biệt:
- Timeout chờ Future.
- Query timeout được cấu hình cho JPA/provider/database.
- HTTP request timeout.
- Cancellation của Future.
- Việc database thực sự hủy statement.

Nếu cần giới hạn thời gian query, cấu hình query timeout phù hợp và kiểm tra driver/database có thực thi hay không. Đừng cho rằng `future.cancel(true)` luôn hủy được JDBC statement hoặc rollback ngay transaction worker.

### 8.4. Async method trả void

Method `@Async` trả `void` không có Future để caller quan sát kết quả. Exception không thể được trả về caller như một Future; Spring dùng `AsyncUncaughtExceptionHandler` cho trường hợp này.

Với công việc cần biết thành công/thất bại, nên trả `CompletableFuture<T>` hoặc ghi nhận trạng thái công việc bền vững trong database/job system.

## 9. Tích hợp với Spring MVC

Spring MVC hỗ trợ các kiểu trả về bất đồng bộ như `CompletableFuture`. Ví dụ:

```java
@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerRepository repository;

    public CustomerController(CustomerRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/search")
    public CompletableFuture<List<CustomerSummary>> search(
        @RequestParam String status
    ) {
        return repository.findSummariesAsync(
            CustomerStatus.valueOf(status)
        );
    }
}
```

Spring MVC có thể giữ request ở trạng thái async trong Servlet container và hoàn tất response khi Future hoàn tất. Servlet request thread ban đầu có thể được giải phóng trong lúc worker thread thực hiện query.

Điều này không có nghĩa toàn bộ request không dùng thread. Worker thread vẫn bị giữ trong khi JDBC blocking; sau khi Future hoàn tất, MVC cần xử lý tiếp để ghi response.

Với lỗi async, hãy dùng exception handling phù hợp của Spring MVC như `@ControllerAdvice` và kiểm tra cách exception được unwrap từ CompletionException/ExecutionException trong phiên bản framework đang dùng.

Không gọi `future.get()` trong controller rồi trả kết quả đồng bộ. Cách đó lại chặn request thread.

## 10. @Async không biến Spring Data JPA thành reactive

### 10.1. JPA vẫn dùng JDBC blocking

Spring Data JPA dựa trên JPA provider, thường là Hibernate, và JDBC driver. Khi gọi query, JDBC thread chờ database thực hiện và trả dữ liệu. `@Async` chỉ quyết định thread nào thực hiện lời gọi.

Vì vậy:
- Một query chậm vẫn chậm.
- Mỗi query đồng thời vẫn tiêu thụ connection khi truy cập database.
- Tăng số worker có thể tăng throughput tới một điểm, sau đó làm database quá tải.
- Thread pool lớn không thay thế tối ưu SQL, index và fetch plan.

### 10.2. Không dùng Flux/Mono như thể JPA là reactive

Spring Data JPA không cung cấp reactive repository execution thực sự dựa trên JPA. Không thể chỉ đổi return type từ `List<T>` sang `Flux<T>` để biến query Hibernate/JDBC thành non-blocking.

Nếu cần reactive end-to-end, dùng:
- Spring WebFlux cho web stack reactive.
- Spring Data R2DBC cho truy cập relational database bằng reactive driver được hỗ trợ.
- Các client reactive cho dịch vụ downstream.

Nếu phải gọi JPA từ WebFlux, đó vẫn là blocking call. Cần cô lập blocking work trên bounded elastic/scheduler phù hợp và kiểm soát concurrency; tốt hơn là tránh trộn blocking JPA vào event-loop thread.

### 10.3. Chọn công nghệ theo nhu cầu

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Query JPA thông thường trong request | Repository đồng bộ |
| Cho phép request thread tiếp tục trong khi query blocking chạy | @Async + CompletableFuture |
| Tác vụ nền cần retry, trạng thái và phục hồi sau restart | Job queue hoặc message broker |
| Reactive database access end-to-end | Spring Data R2DBC với reactive driver |
| Import/export rất lớn | Batch processing, JDBC batch hoặc database bulk tools |

## 11. Giới hạn tải và bảo vệ database

### 11.1. Async có thể làm tăng concurrency

Nếu endpoint nhận 1.000 request trong thời gian ngắn và mỗi request gửi một query async, executor chỉ giới hạn số worker đang chạy; phần còn lại có thể nằm trong queue. Nếu queue quá lớn, độ trễ tăng và heap giữ nhiều task.

Cần:
- Đặt core/max pool hợp lý.
- Đặt queue capacity hữu hạn.
- Đặt max page size và giới hạn input query.
- Áp dụng rate limit hoặc concurrency limit ở API khi cần.
- Theo dõi queue depth, active thread, rejected task và thời gian chờ.
- Giới hạn số query chạy song song trên database.

### 11.2. Xử lý task bị từ chối

Khi executor hết worker và queue đầy, Spring có thể ném `TaskRejectedException`. Hãy chuyển lỗi này thành phản hồi phù hợp hoặc đưa công việc vào hệ thống job bền vững.

Không nên dùng `CallerRunsPolicy` một cách vô thức cho query JPA: policy này có thể chạy task ngay trên thread caller, khiến request vốn muốn async lại bị block. Nếu chọn policy này, phải hiểu rõ đó là backpressure có chủ ý.

### 11.3. Quan sát executor và database

Theo dõi tối thiểu:
- Active worker threads.
- Queue size và số task bị reject.
- Thời gian chờ task trước khi chạy.
- Query duration và connection acquisition time.
- Active/idle connections trong pool.
- Database CPU, lock, slow query và timeout.
- Số Future đang chờ hoàn tất.

Nếu executor có nhiều thread chờ connection, tăng maxPoolSize thường không giải quyết vấn đề. Cần tìm bottleneck ở connection pool hoặc database.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Method @Async vẫn chạy đồng bộ | Chưa bật @EnableAsync hoặc self-invocation | Bật async support và gọi qua Spring proxy/bean khác |
| Caller vẫn bị block | Gọi Future.get()/join() ngay lập tức | Trả Future hoặc compose callback |
| Query async không thấy dữ liệu vừa lưu | Worker chạy trước khi transaction caller commit | Chạy sau commit bằng event/outbox |
| LazyInitializationException | Trả entity có association chưa tải qua ranh giới transaction | Trả DTO hoặc fetch dữ liệu trong worker transaction |
| Transaction không được chia sẻ | Transaction imperative gắn với thread | Mở transaction riêng trên worker thread |
| Database quá tải | Pool/queue cho phép quá nhiều query đồng thời | Giới hạn concurrency và đo connection pool |
| Task bị reject | Executor hết worker và queue | Xử lý TaskRejectedException, điều chỉnh capacity/backpressure |
| Exception bị bỏ qua | Method trả void hoặc Future không được quan sát | Trả CompletableFuture và xử lý exceptional completion |
| Hủy Future nhưng SQL vẫn chạy | Cancellation không đảm bảo hủy JDBC statement | Cấu hình query timeout và kiểm tra driver |
| WebFlux bị nghẽn | Gọi JPA blocking trên event-loop | Cô lập blocking work hoặc dùng R2DBC |

## 13. Kiểm thử async query

### 13.1. Kiểm tra kết quả và exception

Có thể dùng integration test với Spring context thật để bảo đảm `@EnableAsync`, executor và repository proxy được cấu hình:

```java
@SpringBootTest
class CustomerAsyncRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void returnsAsyncQueryResult() throws Exception {
        CompletableFuture<List<CustomerSummary>> future =
            repository.findSummariesAsync(CustomerStatus.ACTIVE);

        List<CustomerSummary> result =
            future.get(5, TimeUnit.SECONDS);

        assertThat(result).isNotNull();
    }
}
```

Timeout trong test chỉ giới hạn thời gian test chờ; nó không tự bảo đảm database query đã bị hủy nếu hết thời gian. Test cần fixture dữ liệu rõ ràng và transaction setup phù hợp.

### 13.2. Kiểm tra thread thực thi

Để xác nhận method chạy trên executor, có thể ghi thread name trong worker hoặc dùng test probe. Thread name prefix như `jpa-query-` giúp quan sát dễ hơn.

Không kiểm tra bằng cách chỉ gọi method trong cùng class vì self-invocation sẽ bỏ qua proxy. Test phải gọi bean được inject từ Spring context.

### 13.3. Kiểm tra transaction và lazy loading

Test nên xác nhận:
- Query chạy trong transaction worker nếu cần.
- DTO chứa đủ dữ liệu sau khi Future hoàn tất.
- Không truy cập lazy proxy sau khi transaction đã đóng.
- Exception database được truyền qua Future.
- Executor từ chối task khi quá tải theo policy đã chọn.
- Nhiều task đồng thời không vượt quá giới hạn dự kiến.
- Shutdown ứng dụng xử lý task đang chạy theo chính sách đã cấu hình.

Dùng database cùng loại production cho test phụ thuộc dialect, lock hoặc transaction behavior. H2 hữu ích cho test nhanh nhưng không thay thế mọi kiểm thử tích hợp.

## 14. Checklist trước khi dùng @Async với JPA

- [ ] Đã bật `@EnableAsync`.
- [ ] Method được gọi qua Spring proxy, không phải self-invocation.
- [ ] Method trả `Future` hoặc `CompletableFuture` phù hợp.
- [ ] Đã chọn executor có tên và giới hạn rõ ràng.
- [ ] Pool size/queue capacity phù hợp connection pool và database.
- [ ] Query có transaction boundary trên worker thread khi cần.
- [ ] Không giả định transaction caller được truyền sang worker.
- [ ] Không gửi EntityManager hoặc managed entity qua thread.
- [ ] DTO/projection chứa đủ dữ liệu trước khi transaction đóng.
- [ ] Exception, timeout, cancellation và task rejection được xử lý.
- [ ] Không chặn caller bằng get()/join() ngay sau lời gọi.
- [ ] Có metric cho executor, connection pool và query latency.
- [ ] Đã xác nhận @Async chỉ chuyển blocking JPA sang thread khác.
- [ ] Nếu cần non-blocking reactive, đã đánh giá R2DBC thay vì đổi return type JPA.

## 15. Kết luận

`@Async` cho phép Spring chạy repository query hoặc service method trên TaskExecutor và trả kết quả qua `Future`/`CompletableFuture`. Muốn hoạt động cần bật `@EnableAsync`, gọi method qua proxy và cấu hình executor có giới hạn. Nó hữu ích khi muốn tách query blocking khỏi request thread hoặc chạy các tác vụ độc lập song song.

JPA/JDBC vẫn blocking. Transaction của caller không tự truyền sang worker thread; worker cần transaction riêng. EntityManager không thread-safe và entity có lazy association có thể trở thành detached sau khi transaction kết thúc, vì vậy DTO/projection thường là kết quả phù hợp hơn.

Async không làm SQL nhanh hơn và có thể tăng tải database nếu pool/queue quá lớn. Hãy điều chỉnh concurrency theo connection pool, xử lý lỗi và timeout rõ ràng, đo queue/query latency. Nếu yêu cầu là non-blocking database access thực sự, hãy chọn stack reactive như Spring Data R2DBC với driver tương thích thay vì xem `@Async` là reactive JPA.