# Truyền ngữ cảnh, an toàn luồng và tránh sử dụng executor không giới hạn trong Spring MVC bất đồng bộ

## 1. Bối cảnh và mục tiêu

Spring MVC hỗ trợ **xử lý request bất đồng bộ trên Servlet stack** bằng `Callable<T>`, `WebAsyncTask<T>`, `DeferredResult<T>`, `ResponseBodyEmitter`, `SseEmitter`, `StreamingResponseBody` và một số reactive return types. Khi handler trả một giá trị bất đồng bộ, thread Servlet ban đầu có thể rời khỏi request sớm trong khi response vẫn mở. Công việc khác tiếp tục trên thread từ executor, thread của callback sự kiện hoặc một hệ thống I/O khác.

Chuyển từ một luồng sang nhiều luồng dẫn đến ba nhóm rủi ro:

1. **Mất ngữ cảnh:** `MDC`/trace ID, `SecurityContextHolder`, `LocaleContextHolder`, `RequestContextHolder`, transaction hay `ThreadLocal` tự định nghĩa không tự đồng bộ giữa mọi thread.
2. **Data race và rò rỉ:** controller/service singleton chia sẻ mutable state không đồng bộ; thread pool tái sử dụng thread giữ lại `ThreadLocal` của request trước; request kết thúc nhưng callback vẫn giữ request/session/stream không còn hợp lệ.
3. **Quá tải tài nguyên:** executor sinh thread không có giới hạn hoặc có queue không giới hạn, blocking task kéo dài và streaming client chậm khiến CPU, heap, connection, disk, database pool và timeout tăng không kiểm soát.

Học xong, bạn có thể giải thích chính xác luồng `Callable` so với `DeferredResult`, cấu hình **`AsyncTaskExecutor` có giới hạn**, truyền MDC/tracing và security context theo cơ chế phù hợp, viết code an toàn luồng, xử lý timeout/rejection/cancellation, và kiểm thử request bất đồng bộ bằng `MockMvc`.

**Phạm vi:** **Java 17+, Spring Framework 6.x, Spring Boot 3.x, Spring MVC Servlet stack**. Đây không phải hướng dẫn WebFlux non-blocking hoặc tutorial riêng cho Java virtual threads. Khả năng chạy trên virtual threads không tự thay thế giới hạn tải đồng thời, kiểm soát tài nguyên hay bảo mật dữ liệu.

## 2. Luồng request ban đầu và luồng async khác gì?

Với `Callable`:

~~~text
Client                         Servlet container             MVC executor
  | GET /api/async/work               |                          |
  |---------------------------------->|                          |
  |                          DispatcherServlet                    |
  |                          gọi controller -> Callable          |
  |                          request.startAsync()                |
  |                          submit Callable ------------------->|
  |                          giải phóng thread Servlet           |
  |                                                             |
  |                                              Callable chạy ở worker
  |                                              tạo DTO / throw error
  |                          <------ kết quả/async dispatch ------|
  |                          DispatcherServlet xử lý lại          |
  |<------------------------- response HTTP ----------------------|
~~~

Trình tự quan trọng:

- Controller được gọi trong **thread phục vụ request ban đầu**.
- Controller trả một đối tượng `Callable<T>`, chứ **không** chạy luôn `call()`.
- MVC dùng `AsyncTaskExecutor` để chạy `Callable` trên worker thread.
- Khi worker hoàn thành, framework **async dispatch** request trở lại Servlet container để hoàn tất response hoặc xử lý exception.
- Mã của ứng dụng không nên giả định mọi đoạn `before/after` ở MVC interceptor/filter chỉ chạy đúng một lần trên cùng một thread; với async có thể có nhiều dispatch phase.

Đối với `DeferredResult<T>`, một hệ thống khác (event listener, message broker callback, scheduler, bounded executor riêng) có thể gọi `setResult` hoặc `setErrorResult`. **MVC không tự chạy công việc producer trong executor của nó** chỉ vì handler trả `DeferredResult`. Đây là khác biệt rất quan trọng cho context propagation.

### Các kiểu trả về thường gặp

| Kiểu trả về | Ai làm công việc tiếp? | Điều cần chú ý |
| --- | --- | --- |
| `Callable<T>` | MVC `AsyncTaskExecutor` | Thread-local context; queue; timeout; result/error |
| `WebAsyncTask<T>` | Executor mặc định hoặc executor riêng nếu cấu hình | Có timeout và callback theo từng tác vụ |
| `DeferredResult<T>` | Producer/callback do ứng dụng hoặc thư viện quản lý | Tự quản lý producer, completion, timeout, cleanup |
| `CompletableFuture<T>` | Executor mà future thực sự được tạo/chạy trên đó | `supplyAsync` không chỉ định executor thường dùng common pool |
| `ResponseBodyEmitter`, `SseEmitter` | Nguồn sự kiện/producer của ứng dụng, hệ thống ghi HTTP | Client chậm; heartbeat; cleanup; bộ nhớ buffer |
| `StreamingResponseBody` | MVC async executor chạy callback ghi `OutputStream` | Blocking writes; client disconnect; executor capacity |
| Reactive return type trên Spring MVC | Bridge qua MVC async mechanism | Ghi Servlet response vẫn blocking ở các điểm tương ứng |

**Async Servlet không đồng nghĩa CPU không còn làm việc.** Nó giúp không giữ thread Servlet ban đầu xuyên suốt thời gian chờ result, nhưng downstream database query, HTTP client, file I/O và response writes có thể vẫn blocking ở nơi khác.

## 3. ThreadLocal: ngữ cảnh gắn với luồng, không gắn với request mãi mãi

Một `ThreadLocal<T>` giữ giá trị theo **thread hiện tại**:

~~~java
private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

TRACE_ID.set("req-42");
String here = TRACE_ID.get(); // "req-42" trên thread vừa set
~~~

Ví dụ này là đoạn Java minh họa trong class/method, không phải toàn bộ chương trình. Nếu executor chạy task trên **thread khác**, `TRACE_ID.get()` trên worker thường là `null`, hoặc tệ hơn là **giá trị cũ bị rò rỉ** do một tác vụ trước không cleanup.

Các holder liên quan trong hệ sinh thái Spring:

| Context | Điểm truy cập | Bản chất |
| --- | --- | --- |
| Correlation/log fields | SLF4J `MDC` | Thường dùng thread-local per logging implementation |
| Security authentication | `SecurityContextHolder` | Strategy mặc định thường thread-local |
| Locale/time zone | `LocaleContextHolder` | Context gắn với thread |
| Request attributes | `RequestContextHolder` | Thường gắn với thread xử lý request |
| Transaction | `TransactionSynchronizationManager` | Thread-bound transaction/resource state |
| Tracing observation | Micrometer Observation/trace context | Có cơ chế scope và context propagation riêng |
| Custom tenant/user metadata | Custom `ThreadLocal` | Phải tự quyết định lifecycle, confidentiality, cleanup |

**Không thể lấy một cơ chế propagate rồi mặc nhiên khẳng định đã mang hết các context còn lại.** Ví dụ MDC có trace ID nhưng worker vẫn có thể không có `SecurityContext` nếu không dùng integration tương ứng; ngược lại một `DelegatingSecurityContextAsyncTaskExecutor` không tự thêm MDC/LocaleContext tùy ý.

### Quy tắc lifecycle

1. **Capture** đúng context tại **điểm giao việc** (submission), không khi class được khởi tạo.
2. **Restore** trong worker ngay trước callback.
3. **Cleanup/restore previous value** trong `finally`, kể cả khi task throw.
4. Không giữ reference sống tới `HttpServletRequest`, `HttpSession`, JPA `EntityManager` hoặc security object mutable quá thời hạn cần thiết.
5. Với tác vụ nền kéo dài sau khi HTTP request hoàn tất, tốt hơn truyền **dữ liệu tối thiểu bất biến** (ID, tenant, principal identifier, traceparent/correlation ID) thay vì copy toàn bộ request scope.

`InheritableThreadLocal` không phải giải pháp an toàn mặc định cho thread pool: thread được tạo/tái sử dụng vào thời điểm khác và có thể giữ ngữ cảnh của công việc không liên quan. Đặc biệt không bật `RequestContextHolder.setRequestAttributes(..., true)` hoặc `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` với mong đợi nó xử lý đúng mọi pooled worker.

## 4. Truyền MDC qua `TaskDecorator` có cleanup

Khi một request có `X-Request-Id`, bạn thường muốn log trong handler, business service và worker đều chứa cùng request ID.

Một `TaskDecorator` có thể capture snapshot MDC lúc task được đưa vào executor, rồi đặt và khôi phục nó trong worker:

~~~java
package com.example.demo;

import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable runnable) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                runnable.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

Đây là **file Java hoàn chỉnh** dùng được trong project Spring Boot có SLF4J. Điểm đáng lưu ý:

- `getCopyOfContextMap()` tạo **snapshot**, không chia sẻ `Map` mutable giữa các request.
- `decorate` được gọi ở phía **submission**, giúp lấy context **trước** khi tác vụ chạy ở worker.
- Task đọc context chỉ trong lúc đang thực thi; finally khôi phục context cũ, không để correlation ID của request A tràn sang request B.
- Nếu task bị exception, `finally` vẫn cleanup. Một số executor đưa cho decorator wrapper khác với user task, nên **đừng dựa vào decorator để bắt mọi exception kinh doanh**; theo dõi future/callback/error handlers và logs.
- Chỉ nên propagate các trường log cần thiết. Không đưa password, cookie, bearer token hoặc PII nhạy cảm vào MDC.

### TaskDecorator không thay controller filter/interceptor

Để MDC có giá trị khi MVC submit `Callable`, request thread cần thiết lập correlation ID **trước khi task được submit**. Filter `OncePerRequestFilter` phù hợp trong ví dụ. Nếu controller tự `MDC.put` rồi `MDC.remove` ngay trong `finally` của handler, MVC có thể submit `Callable` **sau khi handler đã trả về**, khiến decorator chụp một context rỗng. Vì vậy đừng nhầm lifecycle của **controller method** với lifecycle của **Servlet filter chain**.

Một filter cũng cần xử lý dispatch types có chủ đích. `OncePerRequestFilter` có các quy tắc mặc định về async/error dispatch; nếu cần MDC trong cả pha async redispatch, hãy xác minh `shouldNotFilterAsyncDispatch`, filter registration và cách tái lập context trong từng dispatch. Bài demo tập trung MDC khi **worker chạy Callable**, không hứa trace context ở mọi filter/async dispatch.

## 5. Spring Security: context của Callable khác context của executor tùy ý

Với Spring Security 6.x, `SecurityContextHolder` mặc định dùng thread-local strategy. Spring Security có tích hợp với **Spring MVC `Callable`** qua `WebAsyncManagerIntegrationFilter` và `SecurityContextCallableProcessingInterceptor`. Khi filter chain Security hoạt động đúng, integration này có thể đưa `SecurityContext` của request sang thread chạy MVC Callable và dọn theo lifecycle.

**Nhưng điều này không tự bao phủ mọi loại async:**

- `DeferredResult` được một message listener hoàn thành trên thread khác: worker/listener đó không tự có context gốc chỉ vì MVC đã trả `DeferredResult`.
- `CompletableFuture.supplyAsync(...)` gọi `ForkJoinPool.commonPool()` mặc định khi không cấp executor và không tự kế thừa request SecurityContext.
- `@Async` sử dụng executor do Spring async infrastructure chọn, có thể khác hoàn toàn executor dành cho MVC.
- `StreamingResponseBody`, callbacks và producer tự quản lý cần được kiểm tra riêng, không suy luận từ ví dụ `Callable`.
- Async task sau khi user logout hoặc quyền thay đổi không thể xem bản SecurityContext chụp trước đó như một authorization vĩnh viễn.

Để chạy **ứng dụng tự submit task** với Spring Security, có thể dùng `DelegatingSecurityContextAsyncTaskExecutor`:

~~~java
@Bean("securityAwareExecutor")
public AsyncTaskExecutor securityAwareExecutor(
        @Qualifier("boundedWorkerExecutor")
        AsyncTaskExecutor delegate) {

    return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
}
~~~

Đây là **method bean minh họa**, cần dependency Spring Security và bean `boundedWorkerExecutor` đã cấu hình, cũng như import `@Bean`, `@Qualifier`, `AsyncTaskExecutor` và `DelegatingSecurityContextAsyncTaskExecutor`. Với constructor chỉ truyền delegate, executor có thể chụp `SecurityContext` của người submit ở mỗi lần giao task, chạy task trong context đó rồi dọn sau. Nếu đưa một **SecurityContext cố định** vào constructor khác, tất cả task có thể cùng chạy dưới identity đó; đây là quyết định bảo mật riêng, không dùng nhầm trong multi-user web requests.

**Không đăng ký cùng một security context vào nhiều lớp wrapper một cách tùy tiện.** Cần hiểu Spring Security tự tích hợp `Callable` như thế nào, còn custom executor áp dụng cho task nào; kiểm thử với authentication giả lập thay vì chỉ thấy method trả 200 rồi kết luận không rò quyền.

### Authorization phải ở đúng ranh giới

- **Kiểm tra quyền request** trước khi giao việc và trước khi truy cập resource nhạy cảm.
- Nếu task tiếp tục sau một khoảng chờ dài, cân nhắc **kiểm tra quyền lại** khi lấy dữ liệu nhạy cảm, nhất là job nền.
- Chỉ truyền principal ID/tenant ID cần thiết vào task; tránh giữ reference tới mutable Authentication hoặc toàn bộ session dài hơn request.
- Không coi việc có `SecurityContext` trong một worker là bằng chứng nhiệm vụ được phép thực hiện mãi, vì quyền có thể thay đổi.

## 6. Locale, request attributes, tracing và Micrometer

### 6.1. LocaleContextHolder

Trong request MVC, `LocaleContextHolder.getLocale()` có thể dựa vào `LocaleResolver` hoặc cấu hình locale request. Worker tự tạo thông qua `new Thread(...)` không tự có locale ban đầu. Nếu thực thi công việc nền, hãy chụp **`Locale`** như một value object rồi truyền vào service, thay vì buộc service đọc thread-local:

~~~java
Locale locale = LocaleContextHolder.getLocale();
Callable<String> task = () -> renderMessage(locale, "welcome");
~~~

Đây là snippet minh họa trong method có `renderMessage(Locale,String)`. Muốn truyền timezone, chụp thêm `ZoneId` hoặc kiểu domain cần thiết. Cách truyền tham số tường minh giúp test dễ hơn và tránh giữ request attributes đã hết vòng đời.

### 6.2. RequestContextHolder

`RequestContextHolder.currentRequestAttributes()` có thể ném `IllegalStateException` khi không còn request bound với thread. Đừng “vá lỗi” bằng cách set lại nguyên `ServletRequestAttributes` vào một task có thể chạy sau khi HTTP response đã hoàn tất. Request, input stream, output stream và session có lifecycle riêng.

Tốt hơn:

~~~java
String tenantId = validatedTenantIdFromRequest;
String correlationId = validatedCorrelationId;
executor.execute(() -> work(tenantId, correlationId));
~~~

Đây là snippet minh họa khi `executor`, `work` và giá trị đầu vào đã được khai báo/validate. Chọn dữ liệu được sao chép như `String`, `UUID`, immutable record để không giữ servlet request object.

### 6.3. Micrometer Context Propagation

Spring Framework 6.1+ có `ContextPropagatingTaskDecorator` trong `org.springframework.core.task.support` cho những trường hợp dùng Micrometer Context Propagation. Nó hỗ trợ capture/restore logging/observation context trên các thread khác khi được cấu hình đúng:

~~~java
pool.setTaskDecorator(new ContextPropagatingTaskDecorator());
~~~

**Đây là đoạn minh họa bổ sung**, yêu cầu class/dependency Micrometer context propagation thích hợp, phiên bản Spring tương thích, cùng các context accessors đã đăng ký. Không nên khai báo đồng thời decorator tùy biến MDC và decorator Micrometer một cách không kiểm soát; chọn hoặc compose chúng theo nhu cầu thực và kiểm chứng thứ tự restore.

Theo tài liệu Spring MVC, các accessors như `LocaleContextThreadLocalAccessor` và `RequestAttributesThreadLocalAccessor` **cần đăng ký với `ContextRegistry` khi muốn sử dụng**, không tự xuất hiện trong mọi project. Với `ContextSnapshot`:

~~~java
ContextSnapshot snapshot = ContextSnapshot.captureAll();
executor.execute(() -> {
    try (ContextSnapshot.Scope scope = snapshot.setThreadLocals()) {
        doWork();
    }
});
~~~

Đây là snippet khái niệm cho ứng dụng đã cấu hình Micrometer và các imports phù hợp; `executor`/`doWork` là dependencies bên ngoài. Snapshot được chụp ở thread caller; scope khôi phục context trong worker và trả lại trạng thái cũ khi đóng.

**Cần thận trọng:** tự copy request scope qua worker lâu dài có thể giữ đối tượng và dữ liệu quá vòng đời. Context propagation là một chính sách cần thiết kế, không phải cơ chế “clone toàn bộ web request”.

### 6.4. Transaction không mặc nhiên đi cùng thread

`@Transactional` của Spring quản lý transaction resources theo thread. Một `Callable` chạy ở worker **không tự tiếp tục transaction** đã bắt đầu trong controller request thread. Tách transaction ở service chạy **bên trong worker**:

~~~java
return () -> reportService.loadReport(id);
~~~

Ở đây `reportService.loadReport(id)` có thể là public method `@Transactional(readOnly = true)` trên Spring-managed service proxy. Nếu chính method controller được annotate `@Transactional` rồi chỉ return `Callable`, transaction của controller có thể đã kết thúc **trước khi callable được thực thi**.

Không share một JPA `EntityManager` hoặc `Session` thread-bound cho nhiều async tasks. Kiểm tra lazy-loaded entities ở ranh giới async; có thể load DTO cần thiết trong transaction worker.

## 7. An toàn luồng: controller và service là singleton theo mặc định

Spring `@RestController`, `@Service`, `@Component` thường là **singleton beans**. Nhiều request đồng thời gọi cùng một instance. Nếu controller có field mutable và không đồng bộ:

~~~java
@RestController
public class UnsafeCounterController {
    private int count = 0;

    @GetMapping("/counter")
    public int counter() {
        return ++count;
    }
}
~~~

Đây là class minh họa anti-pattern, cần import `@RestController`/`@GetMapping`. Toán tử `++` gồm đọc–tăng–ghi, không atomic. Hai request có thể làm mất increment. Khi async task cũng truy cập field, tình huống race càng rõ.

Nếu thật sự cần counter trong memory (chỉ để demo/metrics đơn giản), dùng:

~~~java
private final AtomicInteger count = new AtomicInteger();

int current = count.incrementAndGet();
~~~

`AtomicInteger` bảo vệ atomic update trong **một process**, nhưng không tự đồng bộ nhiều application instances. Nếu là số dư ngân hàng, business sequence, quota hoặc inventory, cần đồng bộ/transaction/constraint ở storage hoặc service chuyên dụng, không chỉ một AtomicInteger.

### Các kiểu dữ liệu và cơ chế phù hợp

| Loại state | Cách xử lý | Lỗi cần tránh |
| --- | --- | --- |
| Request DTO | Immutable record/local variable | Mutate object chung giữa requests |
| Request ID, tenant ID | Immutable snapshot / explicit parameter | `ThreadLocal` không cleanup |
| Counter đơn giản | `AtomicInteger`, metrics backend | `int++` trên singleton |
| Map chia sẻ in-process | `ConcurrentHashMap` khi hợp đồng phù hợp | `HashMap` đồng thời không khóa |
| Compound update nhiều bước | Lock / atomic compute / DB transaction | Nghĩ ConcurrentHashMap làm mọi chuỗi thao tác atomic |
| File/stream | Một thread sở hữu hoặc synchronization có hợp đồng | Nhiều thread ghi chung `OutputStream` tùy ý |
| Database entity manager | Scope transaction/thread hợp lệ | Share `EntityManager` giữa async tasks |
| Global configuration | Immutable `record`/`final` fields | Ghi mutable config khi xử lý request |

**Không truyền mutable `HashMap`, `ArrayList` hoặc một `StringBuilder` dùng chung vào nhiều callbacks** nếu chúng không có synchronization. Mỗi async request nên sở hữu dữ liệu riêng, hoặc cần concurrency control rõ ràng.

### Atomic không đồng nghĩa an toàn nghiệp vụ

~~~java
int current = counter.get();
if (current < limit) {
    counter.incrementAndGet();
}
~~~

Đoạn trên vẫn có race: hai thread cùng đọc `current < limit`, đều increment vượt quota. Sử dụng thao tác CAS/atomic update hoặc storage transactional tương ứng với business constraint. Đừng rút kết luận “dùng biến atomic nên mọi thứ thread-safe”.

### `volatile` có giới hạn

`volatile` hỗ trợ visibility và ordering nhất định, nhưng `volatile int count` **không làm** `count++` atomic. `synchronized`, `ReentrantLock`, atomic classes hoặc bất biến (immutability) phải được chọn theo thao tác thực tế; không dùng một `synchronized` toàn controller để vô tình serialize mọi request nếu throughput cần cao.

## 8. Tránh executor không giới hạn: ba nguồn rủi ro

Một ví dụ không phù hợp cho tải production:

~~~java
ExecutorService executor = Executors.newCachedThreadPool();
~~~

Một cached thread pool có thể tạo thêm thread khi nhiều tác vụ đang bận mà không có giới hạn thread cố định thích hợp; dưới tải cao, memory và scheduler pressure tăng mạnh. `newFixedThreadPool(8)` giới hạn worker threads nhưng dùng **unbounded queue** mặc định — vẫn có thể gom rất nhiều tác vụ pending và gây out-of-memory/latency lớn. Vì vậy “thread pool có 8 thread” **không** đồng nghĩa “tổng công việc đã được giới hạn”.

Tương tự:

~~~java
CompletableFuture.supplyAsync(() -> slowCall());
~~~

Khi không truyền executor, nó có thể dùng **ForkJoin common pool** thay vì executor MVC mà bạn định cấu hình; thread context/observability/capacity không tự theo rule của MVC. Common pool thích hợp một số công việc CPU-bound có kiểm soát, nhưng đừng dùng như một lối tắt tổng quát cho I/O blocking của request.

### Sức chứa thực tế của ThreadPoolTaskExecutor

Các tham số chính:

- `corePoolSize`: số worker mục tiêu tối thiểu theo policy thread pool.
- `maxPoolSize`: số worker tối đa khi queue đầy và pool cần tăng.
- `queueCapacity`: số task pending cho phép trước khi từ chối hoặc thử tăng worker.
- `keepAliveSeconds`: thời gian idle trước khi non-core threads được thu hồi.
- `RejectedExecutionHandler`: phản ứng khi đã tới capacity; **AbortPolicy** thường an toàn hơn silently dropping task.
- Timeout/cancellation: giới hạn thời gian xử lý, tránh giữ một task vô hạn.
- Monitoring: active threads, pool size, queue depth, rejection count, latency, timeout, disconnect rate.

Ví dụ `core=2, max=4, queue=16`: khi hai worker bận, phần lớn task mới trước tiên vào queue; pool thường chỉ tăng từ 2 lên 4 **sau khi queue đầy**. Khi đã có 4 worker và queue 16 tác vụ, task đến tiếp có thể bị reject. Đây là đặc điểm của `ThreadPoolExecutor` mà `ThreadPoolTaskExecutor` sử dụng theo cấu hình phổ biến; không coi `maxPoolSize=4` là “luôn chạy ngay 4 thread song song” khi queue chưa đầy.

### Đặt queue lớn có thể xấu hơn

Nếu mỗi task mất 5 giây và chỉ 4 worker chạy, một queue 10.000 request có thể giữ rất nhiều object/request snapshots, đồng thời khách hàng chờ vô nghĩa và timeout. Queue giới hạn buộc hệ thống **thừa nhận quá tải** sớm hơn; cần xử lý rejection ở HTTP boundary, capacity planning và đặt giới hạn concurrency tổng thể.

Ngưỡng phù hợp phụ thuộc tài nguyên downstream:
- DB connection pool có 10 connections: 100 worker I/O đồng thời chưa chắc làm nhanh hơn.
- API upstream có rate limit 20 QPS: cần rate limit/circuit breaker/timeout, không tăng thread vô hạn.
- File streaming tới client chậm: một callback blocking có thể giữ worker rất lâu.
- CPU-bound job: tăng thread vượt số CPU cores có thể tăng context switching.

**Little's Law** là trực giác hữu ích: số việc đang xử lý/chờ xấp xỉ arrival rate × thời gian ở hệ thống khi ổn định. Nếu request đến nhanh hơn tốc độ hoàn thành lâu dài, bất kỳ queue hữu hạn nào cũng đầy — giải pháp là giảm tải hoặc tăng năng lực thật, không phải đổi sang queue vô hạn.

## 9. Ví dụ chạy được: bounded MVC executor + MDC propagation

Ví dụ dưới đây có:

- `ThreadPoolTaskExecutor` giới hạn **core=2**, **max=4**, **queue=16**, tên luồng `mvc-worker-`, timeout MVC **5 giây**.
- `MdcTaskDecorator` có snapshot/restore trong finally.
- Một `OncePerRequestFilter` tạo/kiểm tra `X-Request-Id` và đặt `MDC["requestId"]` trong phạm vi filter.
- Controller trả `Callable<WorkResponse>`; worker đọc MDC đã được propagate và trả immutable record.
- MockMvc test dùng `asyncDispatch`, kiểm chứng request/worker trace giống nhau, thread worker khác request handling.
- Chỉ dùng Spring Boot 3.x web/test; **không yêu cầu Spring Security hoặc Micrometer** trong runnable example.

Dự án Maven dùng Java 17+, Spring Boot 3.x, dependencies `spring-boot-starter-web`, `spring-boot-starter-test`, package `com.example.demo`.

Cấu trúc:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/MdcTaskDecorator.java
src/main/java/com/example/demo/AsyncMvcConfig.java
src/main/java/com/example/demo/RequestIdMdcFilter.java
src/main/java/com/example/demo/AsyncWorkController.java
src/test/java/com/example/demo/AsyncWorkControllerTest.java
~~~

### 9.1. Ứng dụng chính

**`DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.2. MdcTaskDecorator.java

Sử dụng toàn bộ nội dung file đã giới thiệu ở mục 4, dưới package `com.example.demo`. Cần **đặt đúng file/class riêng**; không khai báo hai `MdcTaskDecorator` với cùng full-qualified class name.

### 9.3. AsyncMvcConfig.java

~~~java
package com.example.demo;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class AsyncMvcConfig implements WebMvcConfigurer {

    private final AsyncTaskExecutor executor;

    public AsyncMvcConfig(
            @Qualifier("mvcAsyncExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    // Static bean method tránh vòng tham chiếu với chính configuration.
    @Bean("mvcAsyncExecutor")
    public static ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(16);
        pool.setKeepAliveSeconds(30);
        pool.setThreadNamePrefix("mvc-worker-");
        pool.setTaskDecorator(new MdcTaskDecorator());
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return pool;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(5_000L); // milliseconds
    }
}
~~~

Các tham số kích thước chỉ là **demo**. Trong production, cần thiết kế queue/rejection theo SLO, throughput, loại công việc, database pool và số pod/server. Spring Framework docs nhấn mạnh executor mặc định phục vụ MVC async **không phù hợp cho production dưới tải**; cấu hình explicit là khuyến nghị quan trọng.

**Không cần** thêm `@EnableAsync` chỉ để dùng `Callable` của Spring MVC. `@EnableAsync` phục vụ hạ tầng `@Async` riêng, có thể dùng một executor khác.

### 9.4. RequestIdMdcFilter.java

~~~java
package com.example.demo;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestIdMdcFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String candidate = request.getHeader("X-Request-Id");
        String requestId = candidate != null &&
                candidate.matches("[A-Za-z0-9_-]{1,64}")
                ? candidate : UUID.randomUUID().toString();

        String previous = MDC.get("requestId");
        try {
            MDC.put("requestId", requestId);
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove("requestId");
            } else {
                MDC.put("requestId", previous);
            }
        }
    }
}
~~~

**Vì sao filter này không có memory leak đơn giản?**

- Giá trị `requestId` giới hạn tối đa 64 ký tự và chỉ chứa ký tự allowlist, giảm nguy cơ log injection qua header.
- Context được đặt **trước** `DispatcherServlet`, nên lúc MVC submit `Callable`, decorator có thể capture MDC đang active.
- `finally` restore context của thread ban đầu, kể cả exception.
- Worker thread cũng restore context cũ nhờ `MdcTaskDecorator`.
- Filter mặc định có hành vi cụ thể với ASYNC dispatch; demo **chỉ chứng minh propagation ở worker**. Nếu muốn log MDC trong toàn bộ redispatch/filter/controller advice, cần đăng ký/kiểm thử chiến lược phù hợp thay vì mặc định nó vẫn tồn tại.

Trong hệ thống thực, correlation ID có thể được ingress/gateway sinh ra. Không tin mù quáng `X-Request-Id` của mọi client, nhất là khi dùng để liên hệ logs liên tổ chức; áp dụng chính sách đổi tên, validate, sinh ID mới hoặc ánh xạ trace ID tùy trust boundary.

### 9.5. AsyncWorkController.java

~~~java
package com.example.demo;

import java.util.concurrent.Callable;

import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/async")
public class AsyncWorkController {

    @GetMapping("/work")
    public Callable<WorkResponse> work(
            @RequestParam(defaultValue = "demo") String job) {

        if (job.length() > 40) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "job too long");
        }

        // Snapshot dữ liệu request trước khi rời thread Servlet.
        String requestTrace = MDC.get("requestId");

        return () -> {
            // Chạy trên bounded MVC AsyncTaskExecutor.
            String workerTrace = MDC.get("requestId");
            String workerThread = Thread.currentThread().getName();

            return new WorkResponse(
                    job, requestTrace, workerTrace, workerThread);
        };
    }

    public record WorkResponse(
            String job,
            String requestTrace,
            String workerTrace,
            String workerThread) {}
}
~~~

**Ở đây `Callable` không chứa `Thread.sleep`** vì mục tiêu là chứng minh thread context và bounded executor một cách ổn định khi test. Công việc thực sự có thể là gọi service hoặc đọc file, nhưng phải chọn executor phù hợp với mức blocking, giới hạn thời gian và số tài nguyên downstream.

`WorkResponse` là Java record bất biến; không để một mutable shared field trong singleton controller. Cùng `job` và `requestTrace` là snapshots của request, không cần truy cập `HttpServletRequest` trên worker.

### 9.6. Kiểm thử MockMvc bằng asyncDispatch

**`src/test/java/com/example/demo/AsyncWorkControllerTest.java`**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
        .asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
        .get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .status;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncWorkControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void callableCarriesMdcAndUsesBoundedExecutor() throws Exception {
        MvcResult pending = mockMvc.perform(
                        get("/api/async/work")
                                .param("job", "report")
                                .header("X-Request-Id", "req-123"))
                .andExpect(request().asyncStarted())
                .andReturn();

        MvcResult completed = mockMvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.job").value("report"))
                .andExpect(jsonPath("$.requestTrace").value("req-123"))
                .andExpect(jsonPath("$.workerTrace").value("req-123"))
                .andReturn();

        String json = completed.getResponse().getContentAsString();
        assertTrue(json.contains("mvc-worker-"));
    }

    @Test
    void rejectsJobNameThatIsTooLong() throws Exception {
        mockMvc.perform(get("/api/async/work")
                        .param("job", "a".repeat(41)))
                .andExpect(status().isBadRequest());
    }
}
~~~

**Đọc đúng giá trị của test:**
- `request().asyncStarted()` xác nhận request đã vào async handling.
- `asyncDispatch(pending)` đưa kết quả đã hoàn thành qua Servlet/MVC dispatch để hoàn tất response; chỉ lúc đó mới assert JSON.
- `requestTrace=workerTrace` chứng minh MDC propagation trong đường `Callable` demo này.
- `workerThread` chứa prefix `mvc-worker-` chứng minh tác vụ đã chạy trên pool đặt tên.
- Test **không chứng minh pool thật sự chống quá tải** dưới hàng nghìn clients. Cần thêm load/integration tests để đo active threads, queue depth, rejection, timeouts, memory, DB pool và 503.
- Test không thêm Spring Security; nếu ứng dụng thực có Security filters, cấu hình/mock authentication phải tương thích.

Chạy test:

~~~bash
./mvnw test
~~~

Trên Windows dùng `mvnw.cmd test`; nếu thiếu Maven wrapper, dùng `mvn test` khi Maven đã được cài.

### 9.7. Gọi curl

Chạy ứng dụng:

~~~bash
./mvnw spring-boot:run
~~~

Sau đó:

~~~bash
curl -i   -H "X-Request-Id: req-123"   "http://localhost:8080/api/async/work?job=report"
~~~

Kết quả HTTP 200 có JSON **cùng trace ID**:

~~~json
{
  "job": "report",
  "requestTrace": "req-123",
  "workerTrace": "req-123",
  "workerThread": "mvc-worker-1"
}
~~~

**Lưu ý:** tên thread `mvc-worker-1` chỉ minh họa; worker thực tế có thể là `mvc-worker-2` hoặc tên khác theo thứ tự scheduling. Không assert chính xác tên/ID thread. Điều cần kiểm chứng là prefix và trace ID.

Các lệnh xuống dòng dùng dấu `\` của Linux/macOS/Git Bash. Trên Windows PowerShell, dùng `curl.exe` trên một dòng hoặc cú pháp nối dòng của PowerShell.

## 10. DeferredResult: producer chạy đâu và cleanup thế nào?

`DeferredResult` cho phép trả response từ một sự kiện/tác vụ hoàn thành sau này:

~~~java
@GetMapping("/wait-for-message")
public DeferredResult<String> waitForMessage() {
    DeferredResult<String> result =
            new DeferredResult<>(5_000L, "timeout");

    messageBroker.registerListener(payload -> {
        result.setResult(payload);
    });

    result.onCompletion(() ->
            messageBroker.unregisterListener(result));

    return result;
}
~~~

Đây là **minh họa khái niệm**, chưa chạy độc lập vì `messageBroker` và API register/unregister giả định theo hệ thống. Callback producer có thể chạy trên thread broker. Ở những implementation có listener handle, nên lưu đúng subscription/token để unsubscribe trong `onCompletion`, `onTimeout` và `onError` khi thích hợp.

Điểm cần áp dụng:

- **Không tạo một thread riêng trên mỗi request** chỉ để chờ event; dùng infrastructure/event-loop/message broker đã có hoặc bounded executor chuyên trách.
- Đừng giữ `DeferredResult` trong một map vô hạn mà không giới hạn số subscribers hoặc cleanup sau completion/timeout/disconnect.
- Sử dụng `setResult`/`setErrorResult` có tính cạnh tranh (request có thể timeout đồng thời); giá trị trả về của operation nếu available nên được quan sát.
- Context từ request ban đầu **không tự xuất hiện** trên broker listener. Chụp các immutable fields cần thiết, hoặc dùng snapshot/propagation mechanism của producer.
- Nếu producer exception sau khi request timeout, không có guarantee có thể trả body lỗi như khi response chưa commit.

### WebAsyncTask cho một task có timeout riêng

~~~java
@GetMapping("/slow-task")
public WebAsyncTask<String> slowTask() {
    WebAsyncTask<String> task = new WebAsyncTask<>(
            2_000L, () -> slowService.call());

    task.onTimeout(() -> "timeout");
    task.onError(() -> "error");
    return task;
}
~~~

Đây là handler minh họa, cần import `WebAsyncTask`, `@GetMapping` và `slowService` đã được inject. `WebAsyncTask` gắn timeout/callback cho tác vụ MVC `Callable`. **HTTP request timeout không phải cơ chế dừng chắc chắn công việc đã chạy ở worker**; nếu downstream call không hỗ trợ cancel/timeout, nó có thể tiếp tục tốn tài nguyên sau khi client đã nhận response timeout.

Nếu chọn fallback `"timeout"`, phải cân nhắc mã HTTP và contract API; không mặc định một chuỗi fallback với status 200 là lựa chọn đúng cho mọi endpoint.

## 11. Timeout, cancellation, rejection và backpressure

### 11.1. Timeout nhiều lớp

| Tầng | Ví dụ | Tác dụng |
| --- | --- | --- |
| Spring MVC async timeout | `configurer.setDefaultTimeout(5_000)` | Giới hạn thời gian chờ async result theo lifecycle Servlet |
| HTTP client timeout | Connection/read/response timeout khi gọi upstream | Giới hạn thời gian worker chờ bên ngoài |
| DB query timeout | Transaction/query timeout | Giới hạn công việc ở database |
| Queue wait timeout | Deadline trước khi task chạy | Không để request nằm chờ vô nghĩa |
| Reverse proxy idle timeout | Nginx/ingress/CDN | Có thể đóng kết nối trước khi Spring xong |
| Browser/client abort | Người dùng đóng trang, AbortController | Client không cần result nữa; server phải xử lý cleanup |
| Business deadline | Deadline tổng hợp với context/cancellation | Tránh thao tác tiếp tục sau khi hết giá trị |

**Đừng chỉ đặt `setDefaultTimeout` và nghĩ task blocking sẽ bị stop.** Spring/Servlet có thể kết thúc request và giải phóng response, nhưng task đang gọi dịch vụ chậm vẫn cần timeout/cancellation ở I/O tương ứng. Java interruption không phải lúc nào cũng phá được mọi blocking API.

### 11.2. Rejection khi pool đầy

Với `AbortPolicy`, task bị từ chối khi capacity đã hết. Trong Spring Task execution, có thể thấy `TaskRejectedException` hoặc exception được wrapping/tuyến xử lý tương ứng, tùy API/phiên bản.

Một kiến trúc phù hợp:
1. Không nuốt rejection rồi để client treo không có response.
2. Chuyển rejection được nhận diện tại HTTP boundary thành **503 Service Unavailable** hoặc status theo contract, có thể kèm `Retry-After` khi có chiến lược retry thích hợp.
3. **Không tự retry ngay trong request với vòng lặp vô hạn**, vì làm tải nặng hơn.
4. Đặt queue/rejection metrics, alert, rate limiting, admission control.
5. Kiểm thử thật với tác vụ blocking có kiểm soát trong môi trường isolated để chứng minh pool chạm giới hạn và response được xử lý đúng.

Ví dụ đoạn handler ở một tầng đã xác định exception đến được MVC:

~~~java
@RestControllerAdvice
class CapacityErrorAdvice {

    @ExceptionHandler(TaskRejectedException.class)
    ResponseEntity<Map<String, String>> overloaded() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("error", "SERVER_BUSY"));
    }
}
~~~

Đây là **class minh họa**, không phải phần cần bổ sung để runnable demo mục 9. Cần import `@RestControllerAdvice`, `@ExceptionHandler`, `TaskRejectedException`, `ResponseEntity`, `HttpStatus`, `Map`. **Không bảo đảm** mọi exception executor đều đi qua `@RestControllerAdvice`: có lỗi phát sinh trong async submission, filter, executor scheduler hoặc sau response commit. Test end-to-end đúng đường thực tế, bổ sung filter/container error handling khi cần.

### 11.3. Chính sách CallerRuns không luôn tốt cho MVC

`CallerRunsPolicy` dùng thread caller thực thi task khi pool đầy. Nó có thể tạo backpressure ở một số worker pipeline nhưng trong MVC request path, thread caller thường là **Servlet request thread**; nếu tác vụ blocking dài thì bạn có thể chiếm thread Servlet và mất lợi ích của async. Không chọn CallerRuns chỉ vì “không muốn mất tác vụ”, mà phải đánh giá tác động tới toàn server.

**DiscardPolicy** bỏ tác vụ mà không bảo đảm response được hoàn tất, đặc biệt nguy hiểm nếu task tương ứng một `Callable` đang chờ; tránh dùng cho request/response workloads trừ khi thiết kế có completion/error handling rõ ràng.

### 11.4. Semaphore/admission control bổ sung

Một bounded queue hạn chế tổng pending tasks trong một instance, nhưng không giới hạn tuyệt đối số kết nối HTTP/SSE/file streams hay số concurrent DB queries nếu các executor khác cũng hoạt động. Có thể đặt semaphore per downstream hoặc per-tenant quota trước khi submit task, trả 429/503 khi hết slot, và release trong finally.

~~~java
if (!semaphore.tryAcquire()) {
    throw new ResponseStatusException(
            HttpStatus.TOO_MANY_REQUESTS, "too many concurrent jobs");
}
try {
    return compute();
} finally {
    semaphore.release();
}
~~~

Đây là **đoạn minh họa trong service/method chạy công việc**, nơi `semaphore`, `compute` và imports đã tồn tại. Phải đặt `release` đúng lifecycle **khi công việc thực sự kết thúc**, không chỉ khi controller trả `Callable`. Một semaphore in-process không tự giới hạn tổng tải của tất cả application replicas.

## 12. CompletableFuture, @Async và những executor khác nhau

### `CompletableFuture`

~~~java
CompletableFuture<Report> future =
        CompletableFuture.supplyAsync(
                () -> reportService.generate(id),
                boundedExecutor);
~~~

Đây là snippet khi `reportService`, `id`, `boundedExecutor` đã có. Chỉ định **executor có giới hạn** thay vì thả `supplyAsync` vào common pool theo mặc định. Nếu callback cần request context, capture immutable IDs và propagation ở executor. Đừng giữ `HttpServletRequest`/JPA entity sống trên async boundary.

Khi ghép future, phải xét các stages:
- `thenApply` có thể chạy trên thread hoàn thành previous stage.
- `thenApplyAsync` không nhận executor có thể dùng default async facility, thường là common pool.
- `thenApplyAsync(..., boundedExecutor)` rõ nơi chạy tiếp, nhưng vẫn cần thiết kế timeout và propagation.
- `exceptionally`, `handle`, `whenComplete` cần dọn tài nguyên và lỗi đúng contract.

### `@Async`

~~~java
@Service
class ReportService {

    @Async("reportExecutor")
    public CompletableFuture<String> generate() {
        return CompletableFuture.completedFuture("done");
    }
}
~~~

Đây là **class minh họa**, cần imports và bean `reportExecutor` cùng `@EnableAsync` trong cấu hình. Spring `@Async` theo proxy AOP thường chỉ intercept **lời gọi qua Spring proxy**; self-invocation như `this.generate()` trong cùng bean sẽ không tự chuyển thread.

MVC `configureAsyncSupport(...).setTaskExecutor(mvcExecutor)` và executor dùng bởi `@Async` **là hai cơ chế cấu hình khác nhau**. Nếu muốn chia một pool, phải chủ động khai báo/đăng ký cùng bean và đánh giá việc jobs dài làm nghẽn request async. Nhiều hệ thống nên **tách pool theo workload** (quick MVC callbacks, report jobs, streaming), với quota và shutdown policies riêng.

## 13. ResponseBodyEmitter, SSE và StreamingResponseBody: bài toán thread khác nữa

### 13.1. StreamingResponseBody

~~~java
@GetMapping("/download")
public StreamingResponseBody download() {
    return outputStream -> {
        try (InputStream input = fileService.openAuthorizedFile()) {
            input.transferTo(outputStream);
        }
    };
}
~~~

Đây là handler minh họa, cần `fileService` và imports `StreamingResponseBody`, `InputStream`, `@GetMapping`. Chỉ mở source stream **bên trong callback**, không mở trong controller rồi đóng trước khi task async chạy. `transferTo` sao chép theo stream, không yêu cầu đưa toàn file vào heap; nhưng ghi response vẫn có thể **blocking** do client chậm.

Nếu dùng cùng executor cho `Callable` trả JSON và downloads kéo dài, 4 file downloads chậm có thể chiếm hết worker, khiến các request bình thường bị queue và timeout. Cân nhắc tách workload và đặt rate/concurrency limits khi có nhiều stream.

### 13.2. SseEmitter

~~~java
@GetMapping(path = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter events() {
    SseEmitter emitter = new SseEmitter(30_000L);
    emitter.onCompletion(() -> subscriptions.remove(emitter));
    emitter.onTimeout(() -> subscriptions.remove(emitter));
    subscriptions.add(emitter);
    return emitter;
}
~~~

Đây là snippet minh họa giả định `subscriptions` là collection được thiết kế thread-safe (ví dụ concurrent set) và được quản lý tại service. Chỉ phần controller đăng ký emitter **không gửi sự kiện**; producer của ứng dụng phải gửi sự kiện và gọi `complete`/`completeWithError` khi thích hợp.

Trách nhiệm quản lý:

- Giới hạn số SSE clients, thời gian kết nối, buffered outbound events và memory per subscriber.
- Không gửi từ mọi producer thread một cách hỗn loạn vào cùng `SseEmitter` nếu code không điều phối concurrent writes.
- Dùng heartbeat/periodic events để phát hiện client disconnect trong môi trường Servlet; client mất kết nối có thể chỉ được phát hiện khi write xảy ra.
- Cleanup onCompletion/onTimeout/onError, kể cả khi lỗi xảy ra lúc producer đã push.
- Đừng giữ `SecurityContext`, `HttpServletRequest` hoặc các `ThreadLocal` của subscriber suốt một kết nối SSE dài.

Tương tự `ResponseBodyEmitter`: dữ liệu được producer gửi bất đồng bộ nhưng lifecycle callbacks, serialization/blocking writes và resource ownership phải được quản lý riêng.

## 14. Testing đúng: MockMvc, đồng thời và quan sát sản xuất

### 14.1. MockMvc cho correctness

Các assertions cốt lõi với `Callable` là:
- Request ban đầu `asyncStarted`.
- Async result được **dispatch**.
- Kết quả JSON đúng và context cần thiết đã propagate.
- Error/timeout nếu được xử lý theo contract.

Không dùng `Thread.sleep(...)` để đoán async worker đã hoàn thành trong test. `MockMvc` cung cấp async result handling và `asyncDispatch`; test phải chờ đúng lifecycle.

### 14.2. Kiểm thử tải/rejection bằng HTTP thật

Để kiểm tra pool capacity thực sự, chạy server trên HTTP socket thật và tạo nhiều request cùng lúc tới endpoint có tác vụ được chặn bằng synchronization có kiểm soát trong **môi trường test**. Đo:
- Số active worker không vượt configured max.
- Queue không vượt bound.
- Request tiếp theo được reject/timeout đúng policy.
- Không mất `MDC`, không rò context giữa request IDs khác nhau.
- Response lỗi hợp lệ khi pool không còn capacity.
- Recovery sau overload: queue giảm, thread count ổn, memory không tăng mãi.

**Không chạy load test cực lớn trên production** để “kiểm tra unbounded executor” vì có thể làm dịch vụ gián đoạn. Chọn test environment, cấp traffic budget và quan sát metrics.

### 14.3. Spring Boot Actuator / Micrometer metrics

Nếu dùng Spring Boot Actuator và metrics registry tương ứng, bạn có thể giám sát:
- Active thread/pool/queue metrics của executor được bind đúng.
- HTTP server requests duration và status 2xx/4xx/5xx.
- JVM heap, threads, GC pauses, CPU.
- Database connection pool saturation.
- Rate của 503/429/rejection, async timeout, client disconnect.
- Trace/log correlation across workers và downstream calls.

Đừng chỉ dựa vào tổng số HTTP 200. Một hệ thống có queue 10.000 jobs có thể vẫn trả nhiều 200 nhưng p99 latency và bộ nhớ tăng xấu.

### 14.4. Kiểm tra cross-request leakage

Gửi request A có `X-Request-Id: req-A` và B có `X-Request-Id: req-B`. Khi worker thread được tái dùng, A không được nhìn thấy `req-B` và ngược lại. Test tuần tự có thể chưa đủ để bắt race; cần concurrent stress với nhiều request IDs và kiểm tra trace fields trên kết quả/logs.

MDC cleanup trong `finally` là lớp bảo vệ quan trọng, nhưng nếu ứng dụng tự tạo `ThreadLocal` khác, phải kiểm thử và cleanup chính context đó.

## 15. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách làm tốt |
| --- | --- | --- |
| Tin `@Async` tự dùng executor MVC | Hai cơ chế có thể khác nhau | Khai báo rõ executor của từng workload |
| Tin MVC async biến I/O blocking thành non-blocking | Worker vẫn bị block bởi DB/network/stream | Giới hạn concurrency, timeouts và chọn I/O stack phù hợp |
| Dùng cached pool không giới hạn | Thread/memory/scheduler tăng khi tải dồn | Pool/queue bound, admission control |
| Dùng fixed pool với queue mặc định vô hạn | Pending tasks có thể tăng không giới hạn | `ThreadPoolTaskExecutor` queueCapacity rõ |
| Chỉ truyền MDC không truyền SecurityContext | Hai holder/semantics khác nhau | Spring Security integration và wrappers đúng |
| Dùng InheritableThreadLocal trong pool | Thread reuse giữ context không đúng request | Capture/restore/cleanup theo task |
| Tắt MDC trong controller finally trước submit | Async submission có thể sau controller return | Thiết lập ở request filter hoặc capture ID tường minh |
| Giữ `HttpServletRequest` trong job nền | Request có thể hoàn tất/không còn hợp lệ | Immutable snapshots trước submit |
| Chia sẻ `EntityManager` giữa threads | Thread-bound transaction semantics | Service transaction trong worker |
| `volatile int count++` | Increment vẫn không atomic | Atomic/lock/transaction phù hợp |
| Có `ConcurrentHashMap` là mọi logic atomic | Chuỗi read-check-write còn race | Atomic map methods/transactions |
| Nuốt rejection để request “chờ” | Request có thể timeout mà không ai hoàn thành | Báo 503/429 hoặc retry có giới hạn |
| Chỉ có MVC request timeout | Downstream blocking task vẫn chạy | Deadline và cancellation ở từng I/O |
| `CallerRunsPolicy` cho MVC request | Có thể block Servlet request thread | Đánh giá overload semantics riêng |
| Giữ hàng nghìn SSE emitters không cleanup | Memory và connection resource leak | Bound subscriber count, timeout/cleanup |
| Dùng `MockMvc` để chứng minh không thể quá tải | MockMvc không thay HTTP load/production metrics | Integration/load tests đúng workload |
| Log session token trong MDC | Rò credential qua logs | Chỉ propagate correlation metadata cần thiết |

## 16. Câu hỏi ôn tập

**1. Vì sao `Callable<T>` có thể cần propagation nhưng method controller không?**

Controller chạy trên Servlet request thread với context ban đầu; `Callable.call()` chạy sau trên worker thread khác. Các giá trị thread-local không tự có trên worker theo mọi trường hợp.

**2. `TaskDecorator` phải làm gì ngoài `MDC.setContextMap`?**

Capture snapshot khi submit và **restore/clear trong finally** sau worker, để không rò dữ liệu giữa những request khi thread được tái sử dụng.

**3. Spring Security 6.x đã tích hợp MVC Callable thì DeferredResult producer cũng tự có SecurityContext?**

Không. Tích hợp `WebAsyncManagerIntegrationFilter` áp dụng theo lifecycle Callable; event/broker producer hoặc custom executor cần cơ chế propagate riêng.

**4. `newFixedThreadPool(8)` có thực sự giới hạn số tác vụ đang pending không?**

Không. Nó giới hạn thread, nhưng hàng đợi mặc định của factory thường không giới hạn, nên pending tasks/memory vẫn có thể tăng cao.

**5. Với `core=2,max=4,queue=16`, khi nào pool tăng lên worker thứ ba?**

Trong ThreadPoolExecutor phổ biến, sau khi đã có core threads, task mới được queue trước. Khi queue đầy, pool mới tìm cách tăng worker tới max; sau đó reject nếu toàn capacity đã đạt.

**6. `setDefaultTimeout(5000)` có tự interrupt mọi DB query đang block?**

Không chắc. Nó quy định MVC async timeout theo Servlet lifecycle; cần query/socket/call timeout và cancellation phù hợp từng downstream.

**7. `ThreadLocal` của transaction có nên copy sang async worker không?**

Không nên copy thô. Mở transaction riêng trong service thực thi ở worker để thread-bound resources được quản lý đúng.

**8. Vì sao Stream/SSE cần concurrency limit dù đã dùng async?**

Nhiều stream vẫn giữ connections, buffers và có thể giữ threads khi ghi blocking tới client chậm. Async request không tạo tài nguyên vô hạn.

**9. Có thể dùng `CompletableFuture.supplyAsync(...)` không truyền executor cho nhiều blocking HTTP calls?**

Không nên mặc định, vì common pool và context handling/capacity không nhất thiết phù hợp; chỉ định bounded executor cho workload tương ứng.

**10. Nếu thấy log của request A hiện trong request B, kiểm tra gì?**

Kiểm tra MDC/ThreadLocal cleanup trong finally, worker reuse, TaskDecorator chụp context theo thời điểm submit, async dispatch, các executor khác và context nested.

## 17. Checklist triển khai production

1. **Lập sơ đồ async boundaries**: Servlet request, MVC Callable/WebAsyncTask, DeferredResult producer, `@Async`, CompletableFuture, message broker, streaming callbacks.
2. Với mỗi boundary, xác định **ai sở hữu executor**, thread, timeout, exception handling và cleanup.
3. Dùng bounded thread pool/queue, giới hạn concurrent tasks; tránh executor/queue không giới hạn cho công việc blocking.
4. Đặt admission control và overload behavior; trả 503/429 đúng contract thay vì silently dropping.
5. Chụp **immutable request/tenant/correlation context** trước submit; không giữ toàn servlet request hoặc JPA session.
6. Truyền MDC/log/tracing bằng TaskDecorator hoặc Micrometer Context Propagation; cleanup/restore trong finally.
7. Xử lý SecurityContext qua Spring Security integration/wrappers phù hợp, không dùng `InheritableThreadLocal` làm giải pháp chung.
8. Mở transaction trong worker service khi cần; giữ controller/service singleton stateless hoặc synchronize đúng những shared mutable state.
9. Đặt MVC timeout, downstream I/O timeout, deadline/cancellation; đo client disconnect và async errors.
10. Không trộn các stream/downloads lâu với quick-response Callable pool nếu việc chia tài nguyên khiến chúng chèn ép nhau.
11. Test `MockMvc asyncDispatch`, context propagation và response; test HTTP thật dưới tải cho queue/rejection/timeouts.
12. Theo dõi active threads, queue depth, latency p95/p99, DB pool, rejections, memory, trace correlation và leak; điều chỉnh capacity dựa trên đo đạc thay vì đặt max threads rất cao.

## Tài liệu chính thức

- [Spring Framework 6.2 — Asynchronous Requests (MVC)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html)
- [Spring Framework 6.2 — AsyncSupportConfigurer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/config/annotation/AsyncSupportConfigurer.html)
- [Spring Framework 6.2 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2 — TaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/TaskDecorator.html)
- [Spring Framework 6.2 — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Spring Security 6.5 — Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html)
- [Spring Security 6.5 — Servlet MVC Async Security](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/concurrency.html)
- [Micrometer — Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
