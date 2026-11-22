# Ngữ cảnh giao dịch hoặc request không tự truyền sang luồng khác

## 1. Vì sao đổi thread làm mất context?

Trong ứng dụng Spring, nhiều thông tin được gắn với thread hiện tại để các thành phần ở sâu trong call stack có thể truy cập mà không phải truyền tham số qua từng phương thức. Ví dụ:

- Transaction imperative do Spring quản lý thường gắn với thread đang thực thi giao dịch.
- Servlet request context được truy cập qua `RequestContextHolder`, mặc định cũng gắn với thread hiện tại.
- Các dữ liệu như MDC logging hoặc một số context bảo mật có cơ chế lưu theo thread riêng.

Khi code chạy đồng bộ, các phương thức thường được gọi trên cùng một thread nên những thành phần này có thể đọc được context đã thiết lập. Khi công việc được chuyển sang thread khác bằng `@Async`, `Executor`, `CompletableFuture` hoặc một thread pool, thread mới có trạng thái riêng. Spring không tự động chuyển toàn bộ transaction hoặc request context từ thread gọi sang thread thực thi.

Đây là điều cần hiểu khi thiết kế xử lý bất đồng bộ và song song: việc truyền một object, một lambda hoặc một `CompletableFuture` sang executor không đồng nghĩa với việc truyền cả môi trường thực thi của thread ban đầu.

## 2. ThreadLocal và phạm vi của context

`ThreadLocal` lưu một giá trị riêng cho từng thread. Hai thread có thể dùng cùng một biến `ThreadLocal`, nhưng mỗi thread đọc giá trị thuộc về chính nó.

```text
Thread xử lý HTTP request
  ThreadLocal<RequestAttributes> = request A
  Transaction context             = transaction A
             |
             | submit task vào Executor
             v
Thread worker của thread pool
  ThreadLocal<RequestAttributes> = null (hoặc giá trị riêng của worker)
  Transaction context             = không có transaction A
```

Thread worker không tự nhận bản sao transaction hoặc request context của thread gọi. Nếu worker đã từng xử lý một tác vụ khác, nó có thể có trạng thái riêng còn sót lại do code không dọn dẹp đúng cách. Vì vậy, context cần được thiết lập và khôi phục cẩn thận theo từng tác vụ.

`InheritableThreadLocal` có hành vi khác: một thread con mới được tạo có thể kế thừa giá trị từ thread cha tại thời điểm tạo. Tuy nhiên, thread pool thường tạo worker một lần rồi tái sử dụng. Worker đã tồn tại không kế thừa giá trị mới của từng request được submit sau đó. Việc kế thừa cũng có thể khiến worker giữ tham chiếu đến request đã kết thúc. Do đó, `InheritableThreadLocal` không phải cơ chế truyền context an toàn cho thread pool.

## 3. Transaction imperative không được truyền sang thread khác

Với `PlatformTransactionManager` và `@Transactional` theo mô hình imperative, Spring thường lưu transaction resources và synchronization state trong `TransactionSynchronizationManager`, gắn với thread hiện tại.

Khi một phương thức `@Transactional` được gọi qua Spring proxy, transaction manager bắt đầu hoặc tham gia transaction trên thread thực thi phương thức đó. Khi phương thức kết thúc, Spring commit hoặc rollback theo kết quả thực thi.

Nếu phương thức đang ở trong transaction gọi một tác vụ chạy trên thread khác, thread worker không tham gia transaction ban đầu. Ví dụ:

```java
@Service
class OrderService {

    private final Executor taskExecutor;
    private final OrderRepository orderRepository;

    OrderService(Executor taskExecutor, OrderRepository orderRepository) {
        this.taskExecutor = taskExecutor;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void updateAndSchedule(long orderId) {
        Order order = orderRepository.findById(orderId).orElseThrow();
        order.markProcessing();

        // taskExecutor ở đây là executor dùng thread pool, không phải executor chạy trực tiếp trên caller.
        taskExecutor.execute(() -> {
            // Đây là thread khác; transaction của updateAndSchedule không đi theo.
            orderRepository.findById(orderId);
        });
    }
}
```

Trong ví dụ, transaction bao quanh `updateAndSchedule(...)` chỉ quản lý thao tác trên thread gọi. Lambda được executor thực thi ở thread worker và không tự tham gia transaction đó. Nếu worker cần đọc dữ liệu, nó sẽ chạy theo transaction hiện có trên worker (nếu có) hoặc không có transaction, tùy cách repository/service được cấu hình.

Điều này có thể gây ra một số tình huống khó nhận ra:

- Worker đọc dữ liệu trước khi transaction của thread gọi commit nên chưa nhìn thấy thay đổi chưa commit.
- Worker không chia sẻ cùng rollback boundary với thread gọi. Nếu transaction ban đầu rollback, tác vụ đã chạy vẫn có thể tiếp tục.
- Một `EntityManager`, Hibernate `Session`, JDBC `Connection` hoặc transaction resource không được mang sang worker để dùng chung.
- Các thao tác worker có thể commit độc lập, ngay cả khi transaction của request sau đó rollback.

Không nên truyền `Connection`, `EntityManager`, `Session`, transaction status hoặc object persistence đang được quản lý trong transaction qua executor. Hãy truyền ID và dữ liệu bất biến cần thiết; worker tải lại dữ liệu trong transaction của chính nó.

## 4. Tạo transaction riêng cho công việc nền

Nếu tác vụ nền cần truy cập cơ sở dữ liệu, hãy để worker gọi một phương thức transactional thông qua Spring proxy. Transaction được mở trên thread thực thi worker và có vòng đời độc lập.

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderAsyncFacade {

    private final OrderWorker orderWorker;

    OrderAsyncFacade(OrderWorker orderWorker) {
        this.orderWorker = orderWorker;
    }

    @Async("applicationTaskExecutor")
    public CompletableFuture<Void> processAsync(long orderId) {
        orderWorker.process(orderId);
        return CompletableFuture.completedFuture(null);
    }
}

@Service
class OrderWorker {

    private final OrderRepository orderRepository;

    OrderWorker(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void process(long orderId) {
        Order order = orderRepository.findById(orderId).orElseThrow();
        order.completeProcessing();
    }
}
```

Ở đây `OrderAsyncFacade` và `OrderWorker` là hai Spring bean riêng. Khi `processAsync(...)` được gọi qua proxy `@Async`, Spring gửi lời gọi sang executor. Trên worker thread, lời gọi `orderWorker.process(...)` đi qua proxy transaction của bean `OrderWorker`, nên transaction mới được mở ngay trên thread đó.

Phải bật async processing trong cấu hình ứng dụng, ví dụ bằng `@EnableAsync`, và cấu hình executor phù hợp:

```java
@Configuration
@EnableAsync
class AsyncConfiguration {
    // Có thể khai báo applicationTaskExecutor tại đây.
}
```

Một cách khác là dùng `Executor` trực tiếp:

```java
taskExecutor.execute(() -> orderWorker.process(orderId));
```

Điểm quan trọng vẫn là `orderWorker` phải là Spring bean được inject và lời gọi `process(...)` phải đi qua proxy. Nếu tự tạo worker bằng `new OrderWorker(...)` hoặc gọi một phương thức `@Transactional` qua self-invocation trong cùng object, transaction interceptor có thể không được áp dụng.

### REQUIRED và REQUIRES_NEW trong worker

Khi worker bắt đầu chạy trên thread mới, transaction của thread gọi không tồn tại ở đó. Vì vậy:

- `Propagation.REQUIRED` (mặc định) sẽ tham gia transaction đang có trên worker nếu có; nếu không, nó tạo transaction mới.
- `Propagation.REQUIRES_NEW` luôn yêu cầu transaction độc lập trên thread hiện tại. Nếu worker chưa có transaction, nó tạo một transaction mới; nếu có transaction trên worker, transaction đó được tạm treo để mở transaction mới.
- `Propagation.MANDATORY` yêu cầu phải có transaction trên thread hiện tại và sẽ thất bại nếu không có.

`REQUIRES_NEW` không có nghĩa là lấy transaction từ thread gọi rồi chuyển sang worker. Nó chỉ quyết định cách transaction manager xử lý transaction hiện có trên chính thread thực thi phương thức.

## 5. Không gửi tác vụ trước khi dữ liệu cần thiết được commit

Một lỗi thiết kế phổ biến là submit công việc nền ngay bên trong transaction đang ghi dữ liệu, trong khi worker cần đọc dữ liệu vừa tạo:

```java
@Transactional
public void createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(Order.from(command));
    asyncFacade.processAsync(order.getId());
}
```

`processAsync(...)` có thể bắt đầu trước khi transaction của `createOrder(...)` commit. Worker có transaction riêng nhưng vẫn không nhìn thấy dữ liệu chưa commit của transaction ban đầu. Nó có thể không tìm thấy order hoặc xử lý trạng thái cũ.

Nếu tác vụ chỉ nên chạy sau khi transaction thành công, hãy đăng ký công việc theo sự kiện sau commit. Ví dụ:

```java
@Service
class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher events;

    OrderApplicationService(
            OrderRepository orderRepository,
            ApplicationEventPublisher events) {
        this.orderRepository = orderRepository;
        this.events = events;
    }

    @Transactional
    public void createOrder(CreateOrderCommand command) {
        Order order = orderRepository.save(Order.from(command));
        events.publishEvent(new OrderCreated(order.getId()));
    }
}

record OrderCreated(long orderId) {
}

@Component
class OrderCreatedListener {

    private final OrderAsyncFacade asyncFacade;

    OrderCreatedListener(OrderAsyncFacade asyncFacade) {
        this.asyncFacade = asyncFacade;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterOrderCreated(OrderCreated event) {
        asyncFacade.processAsync(event.orderId());
    }
}
```

`@TransactionalEventListener(phase = AFTER_COMMIT)` chỉ kích hoạt listener sau khi transaction phát sự kiện commit thành công. Listener sau đó gọi facade bất đồng bộ để worker bắt đầu xử lý dữ liệu đã commit.

Sự kiện trong bộ nhớ không phải hàng đợi bền vững. Nếu ứng dụng dừng sau khi commit nhưng trước khi tác vụ được submit hoặc hoàn tất, công việc có thể bị mất. Với yêu cầu xử lý phải được giao ít nhất một lần hoặc cần phục hồi sau sự cố, hãy cân nhắc transactional outbox hoặc message broker có cơ chế lưu bền vững.

## 6. Request context cũng gắn với thread

Trong ứng dụng Servlet, `RequestContextHolder` cung cấp `RequestAttributes` của request hiện tại. Spring dùng context này cho một số tính năng như request-scoped bean và truy cập request attributes từ code không nhận trực tiếp `HttpServletRequest`.

Thông thường `DispatcherServlet` thiết lập request context trong lúc xử lý request và dọn context khi dispatch kết thúc. Context mặc định gắn với thread đang xử lý request. Khi code submit một tác vụ tùy ý sang executor, worker không tự động có `RequestAttributes` của request ban đầu.

Ví dụ:

```java
@Service
class AuditAsyncService {

    @Async
    public CompletableFuture<Void> writeAudit() {
        RequestAttributes attributes = RequestContextHolder.getRequestAttributes();
        // Trong worker thread thông thường, attributes có thể là null.
        return CompletableFuture.completedFuture(null);
    }
}
```

Nếu code worker gọi `RequestContextHolder.currentRequestAttributes()` khi không có request context, Spring ném `IllegalStateException` với thông báo tương tự `No thread-bound request found`.

Spring MVC có cơ chế quản lý context cho một số luồng async do chính framework điều phối, chẳng hạn quá trình xử lý `Callable` và lần async dispatch tiếp theo. Điều đó không có nghĩa mọi tác vụ được ứng dụng tự submit bằng `@Async`, `Executor` hoặc `CompletableFuture` đều tự nhận request context. Đặc biệt, callback của `DeferredResult` có thể được gọi trên thread hoàn tất kết quả; không nên giả định thread callback có context của request.

## 7. Không giữ request object hoặc request-scoped bean cho tác vụ nền

Một request-scoped bean được tạo và quản lý theo vòng đời của HTTP request. Scoped proxy có thể tra cứu instance trong request hiện tại khi được gọi. Nếu worker chạy ngoài request context, proxy không có request đang hoạt động để phân giải instance và có thể ném lỗi scope không hoạt động.

Không nên truyền các đối tượng sau vào tác vụ nền rồi sử dụng sau khi request kết thúc:

- `HttpServletRequest`, `HttpServletResponse` hoặc `ServletRequestAttributes`.
- Bean có `@RequestScope` hoặc proxy của bean đó.
- Stream hoặc input body gắn với request mà container có thể đóng sau khi xử lý.
- Các object mutable thuộc request và có thể bị thay đổi đồng thời.

Thay vào đó, hãy trích xuất các giá trị cần thiết khi request còn hoạt động và truyền chúng như dữ liệu đầu vào thông thường:

```java
import java.security.Principal;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

record RequestMetadata(String correlationId, String tenantId, Locale locale) {
}

@RestController
class ExportController {

    private final ExportAsyncService exportService;

    ExportController(ExportAsyncService exportService) {
        this.exportService = exportService;
    }

    @PostMapping("/exports")
    ResponseEntity<Void> startExport(
            HttpServletRequest request,
            Principal principal) {

        RequestMetadata metadata = new RequestMetadata(
                request.getHeader("X-Correlation-Id"),
                request.getHeader("X-Tenant-Id"),
                request.getLocale());

        exportService.start(principal.getName(), metadata);
        return ResponseEntity.accepted().build();
    }
}

@Service
class ExportAsyncService {

    @Async
    public CompletableFuture<Void> start(String username, RequestMetadata metadata) {
        // Dùng dữ liệu đã trích xuất, không truy cập HttpServletRequest.
        return CompletableFuture.completedFuture(null);
    }
}
```

`RequestMetadata` là record bất biến, giữ đúng các giá trị cần cho công việc nền. Trong thực tế, worker có thể dùng correlation ID để ghi log, tenant ID để chọn phạm vi dữ liệu và locale để tạo nội dung. Cần xác thực và kiểm tra các giá trị đầu vào trước khi submit; không mặc định rằng một header do client gửi luôn đáng tin cậy.

## 8. Vì sao không nên bật InheritableThreadLocal cho thread pool?

`RequestContextHolder.setRequestAttributes(attributes, true)` có thể đặt request attributes trong `InheritableThreadLocal`. Thread con được tạo sau đó có thể kế thừa tham chiếu đến attributes. Cách này chỉ có ý nghĩa với thread con mới được tạo trong thời điểm phù hợp và có vòng đời ngắn, được kiểm soát.

Với thread pool, worker thường được tạo trước và tái sử dụng cho nhiều tác vụ. Một worker đã tồn tại không nhận giá trị mới từ thread submit. Nếu worker được tạo khi request A đang hoạt động, nó có thể giữ tham chiếu đến request A rồi tiếp tục được dùng sau khi request A đã kết thúc. Điều này có thể gây rò rỉ dữ liệu giữa request hoặc truy cập tài nguyên đã hết vòng đời.

Vì vậy, không bật chế độ inheritable để cố truyền request context vào executor dùng chung. Hãy truyền dữ liệu nghiệp vụ cần thiết bằng tham số và giữ request lifecycle trong phạm vi xử lý HTTP.

## 9. TaskDecorator và context propagation có kiểm soát

Một số context dạng metadata như MDC logging, trace ID hoặc context quan sát có thể cần được truyền qua executor để log của worker tiếp tục mang cùng correlation/trace. Spring cung cấp `TaskDecorator` để bọc `Runnable` trước khi executor chạy. Micrometer Context Propagation cũng có thể capture và restore các context đã đăng ký thông qua accessor phù hợp.

`ContextPropagatingTaskDecorator` có từ Spring Framework 6.1 và cần thư viện `io.micrometer:context-propagation` trên classpath. Với Gradle và dependency management phù hợp, có thể khai báo:

```groovy
dependencies {
    implementation("io.micrometer:context-propagation")
}
```

Ví dụ cấu hình executor với `ContextPropagatingTaskDecorator`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskDecorator;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class WorkerConfiguration {

    @Bean
    TaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }

    @Bean("applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor(TaskDecorator decorator) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("app-worker-");
        executor.setTaskDecorator(decorator);
        executor.initialize();
        return executor;
    }
}
```

`ContextPropagatingTaskDecorator` dùng Micrometer Context Propagation để khôi phục các context đã đăng ký cho task. Việc truyền phụ thuộc vào các `ThreadLocalAccessor` tương ứng; nó không tự động sao chép mọi biến `ThreadLocal` trong ứng dụng.

Task decorator phù hợp với context metadata có vòng đời và quy tắc truyền rõ ràng. Không đăng ký hoặc truyền Servlet request attributes vào công việc có thể chạy sau khi response kết thúc, trừ khi ứng dụng có cơ chế vòng đời riêng được kiểm soát chặt chẽ. Không dùng decorator để sao chép transaction resources, JDBC connection, `EntityManager` hoặc transaction synchronization sang worker. Transaction cần được mở và đóng đúng cách trên thread worker bằng transaction manager.

Tương tự, nếu cần chuyển `SecurityContext` cho tác vụ async, hãy dùng cơ chế tích hợp của Spring Security như `DelegatingSecurityContextAsyncTaskExecutor` hoặc cơ chế tương ứng với phiên bản đang dùng. Security context là một loại context riêng; việc truyền nó không có nghĩa request context hoặc transaction context cũng được truyền theo.

## 10. Phân biệt imperative transaction và reactive context

Các quy tắc trên nói về transaction imperative, thường được quản lý bằng `PlatformTransactionManager` và gắn với thread. Với Spring WebFlux hoặc reactive data access, transaction do `ReactiveTransactionManager` quản lý được lưu trong Reactor `Context`, không dựa vào một thread cố định.

Reactor `Context` đi theo subscriber trong cùng reactive chain, vì vậy transaction reactive có thể tiếp tục qua các operator đổi scheduler như `publishOn` hoặc `subscribeOn`. Đây là một khác biệt quan trọng so với `ThreadLocal` imperative.

Tuy nhiên, Reactor Context cũng không tự xuất hiện trong mọi công việc tách rời. Khi tạo một subscription độc lập, gọi `CompletableFuture`, submit một `Runnable` trực tiếp vào executor hoặc chuyển dữ liệu sang một hệ thống khác, cần có cơ chế bridge hoặc truyền dữ liệu tường minh. Không nên chuyển một transaction imperative đang hoạt động sang reactive chain hoặc ngược lại bằng cách sao chép ThreadLocal.

| Loại context | Cách Spring thường quản lý | Hành vi khi đổi scheduler/thread |
|---|---|---|
| Transaction imperative | Thread-bound resources và synchronization qua `TransactionSynchronizationManager` | Không tự truyền sang thread khác. |
| Servlet request context | `RequestAttributes` trong `RequestContextHolder`, mặc định thread-bound | Không tự truyền sang tác vụ executor tùy ý; MVC có quản lý riêng cho một số async lifecycle. |
| Reactive transaction | Reactor `Context` do `ReactiveTransactionManager` sử dụng | Theo subscriber trong cùng reactive chain, kể cả khi đổi scheduler; không tự truyền sang subscription độc lập. |
| MDC/tracing/security context | Tùy cơ chế tích hợp và accessor được đăng ký | Cần cơ chế propagation phù hợp, không suy ra từ việc transaction/request context có được truyền hay không. |

## 11. Kiểm thử để xác nhận context không tự truyền

Có thể viết test nhỏ để quan sát sự khác nhau giữa thread request và worker. Ví dụ dưới đây gắn request attributes vào thread test, sau đó đọc `RequestContextHolder` từ một thread của executor:

```java
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.ServletRequestAttributes;

class RequestContextPropagationTests {

    @Test
    void requestAttributesAreNotAutomaticallyAvailableInWorkerThread() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        MockHttpServletRequest request = new MockHttpServletRequest();
        ServletRequestAttributes attributes = new ServletRequestAttributes(request);

        RequestContextHolder.setRequestAttributes(attributes);
        try {
            Callable<RequestAttributes> readWorkerContext =
                    RequestContextHolder::getRequestAttributes;
            RequestAttributes workerAttributes = executor.submit(readWorkerContext)
                    .get(2, TimeUnit.SECONDS);

            assertNull(workerAttributes);
        } finally {
            attributes.requestCompleted();
            RequestContextHolder.resetRequestAttributes();
            executor.shutdownNow();
        }
    }
}
```

Test sử dụng `ThreadLocal` mặc định của `RequestContextHolder`. Worker thread không nhận request attributes được gắn trên thread test. Khối `finally` hoàn tất request attributes, xóa context khỏi thread gọi và dừng executor để test không để lại worker thread.

Có thể kiểm tra transaction tương tự bằng một test Spring chạy trong transaction trên thread test:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@SpringJUnitConfig(TestDatabaseConfiguration.class)
class TransactionContextPropagationTests {

    @Test
    @Transactional
    void callerTransactionIsNotActiveOnWorkerThread() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            assertTrue(TransactionSynchronizationManager.isActualTransactionActive());

            Callable<Boolean> checkWorkerTransaction =
                    TransactionSynchronizationManager::isActualTransactionActive;
            boolean workerHasTransaction = executor.submit(checkWorkerTransaction)
                    .get(2, TimeUnit.SECONDS);

            assertFalse(workerHasTransaction);
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Ví dụ này giả định `TestDatabaseConfiguration` cấu hình một `PlatformTransactionManager` hợp lệ để Spring Test mở transaction cho phương thức test. Transaction test gắn với thread chạy test; executor worker không tự tham gia transaction đó. Trong test thực tế, có thể thay `TestDatabaseConfiguration` bằng cấu hình persistence của ứng dụng.

## 12. Lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Worker không nhìn thấy dữ liệu vừa ghi | Tác vụ chạy trước khi transaction caller commit; transaction caller không truyền sang worker. | Chạy sau commit bằng transactional event listener hoặc outbox; worker mở transaction riêng và đọc lại theo ID. |
| `No thread-bound request found` trong `@Async` | Worker thread không có `RequestAttributes` của HTTP request. | Trích xuất dữ liệu cần thiết từ request và truyền vào tác vụ bằng tham số. |
| Request-scoped bean báo scope không hoạt động | Worker chạy ngoài vòng đời request hoặc không có request context hợp lệ. | Không truy cập request-scoped bean từ tác vụ nền; chuyển dữ liệu cần dùng thành DTO/record bất biến. |
| Transaction rollback nhưng tác vụ nền vẫn ghi dữ liệu | Worker có transaction riêng hoặc chạy ngoài transaction caller. | Chỉ submit sau commit; dùng outbox nếu cần bảo đảm giao việc; xác định rõ transaction boundary của worker. |
| Thread pool dùng nhầm tenant hoặc correlation ID | ThreadLocal không được dọn dẹp hoặc context bị truyền sai vòng đời. | Dùng context propagation có kiểm soát, khôi phục trạng thái trong `finally` và ưu tiên truyền metadata tường minh. |
| `@Transactional` không hoạt động trong worker | Phương thức được gọi bằng self-invocation, object tự tạo hoặc không đi qua Spring proxy. | Đặt phương thức transactional trong bean được inject và gọi qua proxy. |
| Dùng `REQUIRES_NEW` nhưng vẫn không thấy transaction caller | `REQUIRES_NEW` tạo transaction độc lập trên thread hiện tại, không nối transaction từ thread khác. | Truyền ID/dữ liệu và mở transaction mới trong worker; đợi caller commit nếu cần đọc dữ liệu vừa ghi. |
| Reactive transaction mất khi tạo tác vụ riêng | Công việc đã tách khỏi Reactor subscriber/context hiện tại. | Giữ xử lý trong cùng reactive chain hoặc truyền context/dữ liệu bằng cơ chế phù hợp; tránh tự tạo subscription rời rạc. |

## 13. Nguyên tắc thiết kế

- Coi transaction imperative và Servlet request context là context có phạm vi thread và vòng đời cụ thể.
- Không truyền JDBC connection, `EntityManager`, Hibernate `Session`, request/response Servlet hoặc request-scoped bean sang worker.
- Truyền ID và dữ liệu bất biến cần thiết cho tác vụ nền; worker tải dữ liệu trong phạm vi của nó.
- Mở transaction riêng trên worker thông qua một Spring bean có `@Transactional` và được gọi qua proxy.
- Nếu tác vụ phụ thuộc dữ liệu vừa commit, chỉ phát động nó sau commit; dùng transactional outbox khi cần độ bền vững.
- Không dùng `InheritableThreadLocal` như giải pháp tổng quát cho thread pool.
- Dùng `TaskDecorator`, Micrometer Context Propagation hoặc cơ chế chuyên biệt để truyền metadata như trace/MDC/security khi cần; không sao chép transaction resources.
- Phân biệt imperative ThreadLocal context với Reactor Context trong ứng dụng reactive.
- Kiểm thử rõ ràng rằng worker có context nào, transaction nào và dữ liệu nào thay vì dựa vào trạng thái ngầm của thread.

## 14. Kết luận

Transaction imperative và request context của Spring thường gắn với thread đang xử lý. Khi công việc chuyển sang executor hoặc `@Async`, worker không tự tham gia transaction hoặc nhận request attributes của thread gọi. Hãy truyền dữ liệu nghiệp vụ cần thiết một cách tường minh, mở transaction mới trong worker qua Spring proxy và chỉ chạy tác vụ sau commit nếu nó phụ thuộc dữ liệu vừa ghi. Với metadata như trace hoặc MDC, dùng cơ chế context propagation có kiểm soát; không dùng nó để chia sẻ transaction resource hay kéo dài vòng đời của Servlet request.
