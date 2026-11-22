# Spring MVC — Truyền ngữ cảnh khi chuyển sang xử lý bất đồng bộ

## 1. Mục tiêu và vấn đề thực tế

Một HTTP request vào Spring MVC có thể mang theo **ngôn ngữ của người dùng**, thông tin request, danh tính đã xác thực, mã đối chiếu (request ID), trace/span ID và trạng thái giao dịch. Khi controller chạy đồng bộ trên một Servlet thread, Spring thường gắn một số dữ liệu này với thread hiện tại. Nếu công việc chuyển sang thread khác bằng `@Async`, `CompletableFuture` hoặc executor, chúng **không tự động xuất hiện đầy đủ** ở thread mới.

Ví dụ:

~~~java
Locale locale = LocaleContextHolder.getLocale();
String requestId = MDC.get("requestId");
~~~

Trong handler đang xử lý request, `locale` có thể là `vi_VN` và `requestId` là một UUID. Tuy nhiên, nếu bạn chạy chính hai dòng đó trong `CompletableFuture.supplyAsync(...)` trên common pool, kết quả có thể trở thành locale mặc định của máy chủ và `requestId == null`. Điều đó gây sai ngôn ngữ, mất khả năng đối chiếu log, hoặc nghiêm trọng hơn là sử dụng sai thông tin bảo mật.

Sau bài học, bạn có thể:

- Phân biệt **business data** được truyền qua tham số tường minh và **execution context** gắn với thread.
- Hiểu `LocaleContextHolder`, `RequestContextHolder`, SLF4J `MDC`, `SecurityContextHolder`, Micrometer tracing/context propagation và phạm vi phù hợp của mỗi loại.
- Giải thích vòng đời Servlet async của `Callable`, `DeferredResult`, `CompletionStage` và `@Async` — chúng không đồng nghĩa với nhau.
- Thiết kế `TaskDecorator` **capture khi submit**, **restore khi chạy**, **cleanup trong finally**; tránh context leak qua thread pool.
- Biết khi nào dùng `ContextPropagatingTaskDecorator`/Micrometer Context Propagation và khi nào dùng Spring Security `DelegatingSecurityContextAsyncTaskExecutor`.
- Xây dựng ví dụ Java 17+ / Spring Boot 3.5.0 với `@Async`, locale, request ID, HTTP response và MockMvc async dispatch.
- Nhận diện các giới hạn về request/session lifecycle, SecurityContext, transaction, tracing, timeout, thread pool, data privacy và propagation qua service khác.

**Phạm vi:** Spring MVC (Servlet stack) của Spring Framework 6.2.x. Không đồng nhất giải pháp này với Spring WebFlux/Reactor Context; các môi trường dùng reactive stack cần thiết kế khác.

## 2. Context là gì? Vì sao đổi thread làm mất context?

**Context** là dữ liệu đi kèm một lần thực thi mà nhiều thành phần cần truy cập nhưng không phải lúc nào cũng được truyền trực tiếp qua tham số phương thức: locale, trace ID, request metadata, authentication, v.v.

Trong Java, `ThreadLocal<T>` lưu giá trị gắn với **một thread**. Thread khác có ThreadLocal riêng:

~~~java
private static final ThreadLocal<String> CURRENT_REQUEST =
        new ThreadLocal<>();
~~~

Với một thread pool, worker thường được tái sử dụng để xử lý nhiều tác vụ của nhiều người dùng. Nếu không dọn ThreadLocal sau khi chạy, ngữ cảnh của request cũ có thể lẫn sang tác vụ mới.

### 2.1. Chương trình Java 17 độc lập: quan sát context mất khi đổi thread

Lưu vào file `ThreadLocalDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadLocalDemo {
    private static final ThreadLocal<String> REQUEST = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            REQUEST.set("req-A");

            Future<String> without = pool.submit(REQUEST::get);
            System.out.println(without.get() == null);

            String captured = REQUEST.get(); // Capture trên caller thread.

            Future<String> with = pool.submit(() -> {
                String previous = REQUEST.get();
                try {
                    REQUEST.set(captured); // Install trên worker.
                    return REQUEST.get();
                } finally {
                    if (previous == null) {
                        REQUEST.remove();
                    } else {
                        REQUEST.set(previous);
                    }
                }
            });
            System.out.println(with.get());
        } finally {
            REQUEST.remove();
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac ThreadLocalDemo.java
java ThreadLocalDemo
~~~

Stdout:

~~~text
true
req-A
~~~

**Ý nghĩa:** request context không tự chuyển sang worker. Phải capture tại nơi còn ngữ cảnh, install trong thread xử lý và restore/clear sau khi kết thúc. `finally` rất quan trọng khi task ném exception. Không thay thế bằng việc set context một lần lúc tạo thread pool, vì pool phục vụ nhiều request.

### 2.2. Những context thường gặp trong Spring

| Cơ chế | Chứa dữ liệu gì? | Phạm vi mặc định và điều cần nhớ |
| --- | --- | --- |
| `LocaleContextHolder` | `LocaleContext`, có thể kèm timezone | ThreadLocal của Spring; dùng cho localization/formatting |
| `RequestContextHolder` | `RequestAttributes`, thường `ServletRequestAttributes` | Gắn với request/thread; request object có vòng đời hữu hạn |
| `SecurityContextHolder` | `SecurityContext` với `Authentication` | Thường thread-local; propagation phải có cơ chế bảo mật phù hợp |
| SLF4J `MDC` | Map chuỗi phục vụ structured logging, correlation ID | Thường thread-local trong log backend; cần copy/restore |
| Micrometer Observation/Tracing | Observation, trace/span context | Cơ chế riêng được instrumentation và context propagation quản lý |
| `TransactionSynchronizationManager` | Resource/transaction synchronization state | Ràng buộc với thread/transaction; không copy tùy tiện sang worker |
| HTTP session | Trạng thái phiên người dùng, lưu server-side | Không phải ThreadLocal; không biến session thành context của task một cách ngầm định |
| `@SessionAttributes` | Model attributes được giữ qua các request MVC | Là lifecycle của model/session, **khác** async thread context |

Đặc biệt, **ngôn ngữ được resolve từ HTTP request** không tự biến thành thuộc tính của task background. Bạn phải quyết định: một tác vụ cần đúng locale của người dùng lúc submit, hay locale mới được chọn sau đó? Thường nên capture một giá trị bất biến (ví dụ `Locale` và user ID đã được cho phép) ngay khi lên lịch.

## 3. LocaleContextHolder và RequestContextHolder trong MVC

Spring MVC thường xác định locale từ `LocaleResolver`/`LocaleContextResolver`. Ví dụ cấu hình mặc định có thể sử dụng `Accept-Language: vi-VN`. Trong request handler, Spring gắn locale context với thread phục vụ request:

~~~java
@GetMapping("/welcome")
@ResponseBody
String welcome() {
    Locale locale = LocaleContextHolder.getLocale();
    return locale.toLanguageTag();
}
~~~

Trong ngữ cảnh request thích hợp với `Accept-Language: vi-VN`, kết quả là `vi-VN`. Đây là fragment handler; cần class/controller và imports nếu đưa vào ứng dụng.

**Phân biệt:**

- `LocaleContextHolder.getLocale()` trả `Locale` theo context hiện tại hoặc fallback locale. Việc gọi thành công **không chứng minh** locale của request đã được propagate.
- `LocaleContextHolder.getLocaleContext()` cho phép lấy đối tượng `LocaleContext`; nếu ngữ cảnh hỗ trợ timezone, phần đó có thể được bảo toàn khi propagate đúng context.
- `LocaleContextHolder.setLocaleContext(context)` thiết lập context cho thread đang chạy; `resetLocaleContext()` xóa nó khỏi thread.
- `RequestContextHolder.currentRequestAttributes()` có thể ném `IllegalStateException` nếu không có request attributes gắn vào thread. `getRequestAttributes()` trả null khi không có.

### 3.1. Vì sao không copy ServletRequestAttributes bừa bãi?

Request chỉ sống trong vòng đời HTTP do Servlet container điều khiển. Khi `@Async` tạo **background job tiếp tục chạy sau khi response đã hoàn tất**, việc giữ tham chiếu `HttpServletRequest`, `HttpSession` hoặc `ServletRequestAttributes` có thể gây:

1. Truy cập request không còn hợp lệ sau request completion.
2. Giữ reference tới object lớn, session hoặc dữ liệu nhạy cảm lâu hơn dự định.
3. Giả định session/security state vẫn bất biến, trong khi người dùng có thể đăng xuất hoặc đổi quyền.
4. Race condition nếu nhiều threads cùng truy cập request/response mutable.

**Ưu tiên:** chắt lọc dữ liệu cần thiết trên request thread và truyền rõ vào task:

~~~java
record JobContext(
        String requestId,
        Locale locale,
        String authorizedUserId) {
}

// Lấy trên request thread, sau khi đã kiểm tra quyền.
JobContext context = new JobContext(requestId, resolvedLocale, userId);
executor.execute(() -> service.perform(jobId, context));
~~~

Đây là fragment kiến trúc, cần `requestId`, `resolvedLocale`, `userId`, `jobId` và service phù hợp. Không đưa vào immutable context password, bearer token hoặc toàn bộ session. **Một user ID không tự cấp quyền**: background job có thể cần re-check quyền hoặc service identity tùy thời điểm và chính sách.

### 3.2. Chú ý timezone

Locale như `vi-VN` không tự định nghĩa timezone. Nếu yêu cầu hiển thị giờ của người dùng, context có thể cần `ZoneId` độc lập:

~~~java
record DisplayContext(Locale locale, ZoneId zoneId) {
}
~~~

Import `java.util.Locale` và `java.time.ZoneId`. Khi gửi task vào hàng đợi hoặc tiến trình khác, gửi các giá trị bất biến có hợp đồng rõ, không dựa vào JVM default timezone.

## 4. Các loại xử lý bất đồng bộ không giống nhau

### 4.1. Spring MVC Callable

~~~java
@GetMapping("/report")
@ResponseBody
public Callable<String> report() {
    return () -> reportService.generate();
}
~~~

Spring MVC chuyển Servlet request sang async mode, submit `Callable` lên `AsyncTaskExecutor` được cấu hình, rồi sau khi có kết quả sẽ **ASYNC dispatch** để hoàn tất HTTP response.

Không nhầm việc Spring có lifecycle riêng cho MVC `Callable` với việc mọi `ThreadLocal` tùy ý đều tự theo sang thread khác. Framework và các interceptor có thể thực hiện một số context binding nhất định; với MDC/custom ThreadLocal vẫn cần kiểm thử và cấu hình có chủ đích.

### 4.2. DeferredResult

~~~java
@GetMapping("/jobs/{id}/wait")
@ResponseBody
public DeferredResult<String> waitForJob(@PathVariable String id) {
    DeferredResult<String> result = new DeferredResult<>(10_000L);
    registry.register(id, result);
    return result;
}
~~~

Khi một thread khác có kết quả:

~~~java
result.setResult("done");
// Hoặc result.setErrorResult(exception);
~~~

Đây là hai fragment mô tả ý tưởng; `registry` và `result` phải được quản lý trong ứng dụng thực. `DeferredResult` không tự tạo worker task: **ứng dụng chủ động hoàn thành nó** từ thread/callback khác. Khi kết quả đến, MVC dispatch lại để trả response. Cần xử lý `onTimeout`, `onCompletion`, cleanup registry và tránh hoàn tất hai lần.

Không giữ Servlet request hoặc locale holder xuyên suốt vòng đời DeferredResult. Capture rõ context khi đăng ký, dùng khi hoàn tất nếu cần; ngữ cảnh mới ở callback không mặc nhiên là ngữ cảnh ban đầu.

### 4.3. CompletionStage/CompletableFuture

~~~java
@GetMapping("/summary")
@ResponseBody
public CompletableFuture<String> summary() {
    return CompletableFuture.supplyAsync(() -> "ready", executor);
}
~~~

Spring MVC có thể thích ứng `CompletionStage`/`CompletableFuture` thành một kết quả HTTP async. Tuy nhiên **phần task do chính bạn submit** lên executor khác sẽ sử dụng thread của executor đó. Nếu dùng:

~~~java
CompletableFuture.supplyAsync(() -> work());
~~~

mà không chỉ định executor, Java thường dùng `ForkJoinPool.commonPool()`. Không giả định MDC, locale, SecurityContext hoặc transaction đi theo common pool.

Tương tự, các stage kiểu `thenApplyAsync`, `thenComposeAsync` hoặc callback do thư viện bên ngoài gọi có thể chạy trên thread khác. Nếu chỉ propagate **stage đầu tiên** mà stage sau chạy trên executor khác, context lại có thể mất. Thiết kế propagation tại **mọi boundary có đổi thread**.

### 4.4. @Async

~~~java
@Service
class ReportService {
    @Async("contextExecutor")
    public CompletableFuture<String> generate() {
        return CompletableFuture.completedFuture("done");
    }
}
~~~

`@Async` trong Spring thường sử dụng proxy/interceptor để submit method invocation lên executor. Phải bật `@EnableAsync` và gọi method qua Spring-managed bean/proxy (ví dụ controller inject service). **Self-invocation** từ một method của cùng instance gọi method `@Async` khác thường bỏ qua proxy nên chạy đồng bộ.

`@Async` là **cách chạy method ở worker**, không phải cơ chế tự propagate mọi loại context. `ContextPropagatingTaskDecorator` hoặc cơ chế tương đương phải được gắn đúng executor.

### 4.5. Bảng so sánh

| Công cụ | Ai chọn/schedule worker? | HTTP response còn chờ? | Context cần chú ý |
| --- | --- | --- | --- |
| MVC `Callable<T>` | MVC AsyncTaskExecutor | Có, Servlet async | Lifecycle MVC, custom MDC/tracing, executor |
| MVC `DeferredResult<T>` | Ứng dụng/event source tạo kết quả | Có, tới result/timeout | Callback thread và cleanup |
| Controller trả `CompletableFuture<T>` | Bạn hoặc library tạo future | Có, tới future complete/timeout | Executor của tất cả stages |
| Service method `@Async` | Spring AOP async executor | Không tự bảo đảm controller đang chờ; phụ thuộc return type | Proxy, TaskDecorator, SecurityContext |
| Scheduled/background job | Scheduler/queue | Thường không còn HTTP request | Truyền context immutable/re-auth theo chính sách |
| Reactor/WebFlux | Reactive scheduling/context | Theo reactive pipeline | Reactor Context, không tự dựa ThreadLocal |

Khi Servlet request chuyển async, container thread ban đầu được trả về pool nhưng HTTP response có thể vẫn mở. Kết thúc async processing thường gồm một ASYNC dispatch; filter mappings và async-supported phải được cấu hình đúng để middleware hoạt động như mong đợi.

## 5. Quy tắc capture → install → execute → restore

Một cách an toàn để chuyển context qua thread boundary:

~~~text
HTTP request thread                         Pool worker thread
LocaleContextHolder = vi_VN
MDC.requestId = abc-123
       |
       | submit(task)
       | -- CAPTURE snapshot --> locale=vi_VN, mdc={requestId:abc-123}
       |                         |
       |                         | INSTALL vào worker
       |                         | EXECUTE công việc
       |                         | finally RESTORE worker state cũ
       |                         |
HTTP handler được giải phóng                Worker tái sử dụng an toàn
~~~

Quan trọng:

- **Capture ở thời điểm submit**, khi caller thread còn context hợp lệ. Nếu capture lúc worker chạy, bạn có thể đã mất context nguồn.
- Chỉ chuyển các trường **thực sự cần thiết**, không copy toàn bộ request object hoặc ThreadLocal không rõ tác dụng.
- **Restore trạng thái trước đó**, không chỉ gán null tùy tiện; một worker có thể nằm trong một context lồng nhau.
- Dùng `try/finally` kể cả khi task ném exception hay bị hủy.
- Chọn context lifetime đúng: HTTP request đã hoàn thành thì background task không còn quyền phụ thuộc live ServletRequest.
- Bảo mật: không giữ một authentication object mutable từ request quá lâu hoặc truyền nhầm sang task của người khác.

### 5.1. TaskDecorator ở Spring Framework

Spring cung cấp `org.springframework.core.task.TaskDecorator`. Với `ThreadPoolTaskExecutor`:

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(2);
executor.setMaxPoolSize(4);
executor.setQueueCapacity(50);
executor.setThreadNamePrefix("ctx-");
executor.setTaskDecorator(new LocaleAndMdcTaskDecorator());
executor.initialize();
~~~

Đây là fragment từ lớp cấu hình hoàn chỉnh ở mục 9. `TaskDecorator` bọc callback chuẩn bị chạy. Nó có thể được áp dụng cho wrapper Runnable của task chứ không nhất thiết là đúng Runnable do user gửi; vì vậy đừng dựa vào TaskDecorator để bắt/quan sát mọi exception trong các `Future`. Mục đích ở đây là **context propagation**, không phải toàn bộ error handling.

### 5.2. Dọn context quan trọng như truyền context

Sai:

~~~java
return () -> {
    MDC.put("requestId", capturedId);
    task.run();  // Nếu task ném exception, MDC tồn tại trên pooled thread.
};
~~~

Đúng về nguyên tắc:

~~~java
return () -> {
    String previous = MDC.get("requestId");
    try {
        MDC.put("requestId", capturedId);
        task.run();
    } finally {
        if (previous == null) MDC.remove("requestId");
        else MDC.put("requestId", previous);
    }
};
~~~

Đây là phiên bản đơn giản cho **một key**. Muốn propagate đầy đủ MDC, dùng `MDC.getCopyOfContextMap()` và `MDC.setContextMap(...)` kèm clear/restore (xem dự án). Dù vậy, chỉ có những key đã qua privacy review mới nên được đặt trong MDC; context propagation không thay thế redaction.

## 6. SecurityContext: truyền một cách có kiểm soát

Spring Security thông thường quản lý `SecurityContext` bằng `SecurityContextHolder`, thường dựa trên thread-local. Worker mới không tự có danh tính của request.

Spring Security cung cấp:

- `DelegatingSecurityContextRunnable` / `DelegatingSecurityContextCallable`.
- `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextTaskExecutor` và `DelegatingSecurityContextAsyncTaskExecutor`.
- Tích hợp với các dạng Spring MVC async nhất định, ví dụ Callable; không được suy ra rằng mọi executor tùy biến hay background job được bảo vệ giống nhau.

Một ví dụ minh họa executor wrapper:

~~~java
AsyncTaskExecutor delegate = configuredExecutor;
AsyncTaskExecutor secured =
        new DelegatingSecurityContextAsyncTaskExecutor(delegate);
~~~

Cần import `org.springframework.core.task.AsyncTaskExecutor` và `org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor`, cùng dependency Spring Security. Với constructor nhận delegate mà không cấp explicit context, wrapper capture security context khi task được submit theo hợp đồng của class, chạy dưới context đó và dọn sau khi xong.

**Không đặt `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` như một "chữa nhanh" cho pooled workers.** Thread trong pool được tạo rồi tái dùng ở những thời điểm khác nhau, giá trị inherited có thể cũ hoặc không tương ứng request. Cũng đừng sao chép một mutable `Authentication` rồi tùy tiện chuyển qua nhiều task không đáng tin cậy.

Quan trọng hơn, background job dài hạn nên nhận **user ID, tenant ID và các business facts cần thiết** rồi xác định cơ chế xác thực/phân quyền thích hợp khi thực thi; việc copy context tại thời điểm enqueue không có nghĩa quyền đó vẫn hợp lệ nhiều giờ sau. Tuân thủ least privilege và không tiết lộ token.

## 7. Micrometer Context Propagation và tracing

Spring Framework 6.2 có thể tích hợp thư viện **Micrometer Context Propagation**. Nó cung cấp cơ chế chụp các `ThreadLocalAccessor` đã đăng ký và phục hồi giá trị qua thread boundaries.

Ví dụ hướng dùng `ContextSnapshot` (minh họa, cần dependency và registry phù hợp):

~~~java
ContextSnapshot snapshot = ContextSnapshot.captureAll();

executor.execute(() -> {
    try (ContextSnapshot.Scope scope = snapshot.setThreadLocals()) {
        process();
    }
});
~~~

Import:

~~~java
import io.micrometer.context.ContextSnapshot;
~~~

**Không tự suy ra `captureAll()` sẽ chứa mọi ThreadLocal.** Chỉ những loại context có `ThreadLocalAccessor` đã được đăng ký mới được capture/restore. Spring cung cấp `LocaleContextThreadLocalAccessor` và `RequestAttributesThreadLocalAccessor`, nhưng trong tài liệu Spring MVC 6.2 các accessor này **không được đăng ký tự động**; cần đăng ký với `ContextRegistry` nếu muốn dùng. Xem xét đặc biệt kỹ request attributes lifetime.

Spring 6.1+ có `ContextPropagatingTaskDecorator`:

~~~java
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
~~~

Import `org.springframework.core.task.support.ContextPropagatingTaskDecorator`; cần thư viện Micrometer Context Propagation thích hợp trên classpath. Decorator này hỗ trợ logging/observation context khi có accessor đúng; nó gây overhead khi tasks rất nhỏ và không thay thế quản lý executor capacity, timeouts, security authorization hay request lifecycle.

### 7.1. Tracing xuyên thread và xuyên dịch vụ là hai việc khác nhau

Trong cùng process, task decorator/context snapshot có thể restore tracing/observation context cho worker. Khi Service A gọi Service B qua HTTP, cần **inject/extract tracing headers** theo chuẩn như W3C `traceparent` qua HTTP client instrumentation. Việc có MDC.requestId trên A không tự làm B nhận đúng ID.

Nếu ứng dụng đã dùng Micrometer Tracing/OpenTelemetry, ưu tiên cơ chế context propagation/instrumentation có sẵn của hệ đó; không tự tạo thêm hệ span/trace giả mạo. Một trace có thể gồm nhiều span, và custom requestId không bắt buộc bằng traceId.

### 7.2. Tránh double propagation và context cũ

Khi gắn nhiều task decorators, security wrappers, tracing interceptors hoặc custom MDC propagation lên cùng executor, phải xác định thứ tự và quyền sở hữu key. Nếu hai cơ chế ghi cùng key MDC/LocaleContextHolder, giá trị sau cùng có thể không như mong đợi. Hãy test dưới nhiều requests đồng thời, bảo đảm restore đúng scope trước khi worker nhận task mới.

## 8. Hướng sản xuất: chọn mô hình đúng theo nhu cầu

| Mục đích | Hướng khuyến nghị |
| --- | --- |
| Formatter/message theo locale trong task ngắn | Truyền `Locale`/`ZoneId` tường minh, hoặc decorator đã kiểm thử |
| Request ID cho logs `@Async` | Capture/copy MDC tại submission; restore/clear trong worker |
| Spring Security authentication tại task ngắn | Security delegating executor hoặc integration được hỗ trợ |
| Task nền kéo dài sau HTTP response | Truyền immutable business context, không giữ ServletRequest |
| Trace cross-thread/cross-service | Micrometer/OpenTelemetry context propagation và HTTP instrumentation |
| Async trả HTTP response | MVC Callable/DeferredResult/CompletionStage + timeout/interceptor/ASYNC dispatch |
| Chờ external event | DeferredResult hoặc asynchronous messaging với lifecycle cleanup |
| Nhiều công việc rất nhỏ | Đánh giá overhead snapshot/decorator, batch và pool sizing |
| Job qua queue/message broker | Serialize explicit metadata được phép, không gửi Java ThreadLocal/SecurityContext object |

Một số ranh giới quan trọng:

- **Transaction:** transaction-bound resources của `@Transactional` không tự chuyển theo pooled worker. Không copy `TransactionSynchronizationManager` sang thread khác để "chia sẻ" một database transaction. Hãy mở transaction mới theo nghiệp vụ hoặc tổ chức lại boundary.
- **Persistence:** JPA entity lazy proxies có thể không truy cập được ngoài transaction; DTO/projection có dữ liệu cần thiết nên được chuẩn bị trước khi gửi background job.
- **Timeout/cancellation:** nếu HTTP async timeout trước khi task hoàn tất, worker có thể vẫn đang chạy tùy cấu hình; cần xử lý cancel, shutdown, idempotency và tránh ghi response khi đã committed.
- **Thread pool:** queue không giới hạn có thể tích tụ tasks và giữ captured context/PII quá lâu. Chọn pool/queue/rejection policy có giám sát.
- **Error handling:** exception trong `CompletableFuture` cần được xử lý với `exceptionally`, `handle` hoặc MVC async exception path phù hợp; không bỏ qua future lỗi.
- **MDC memory/privacy:** đừng capture toàn bộ MDC nếu ứng dụng chứa token/PII trong đó. Lọc các key như requestId/traceId đã được cho phép.
- **ASYNC dispatch:** Servlet filters có thể cần mapping `DispatcherType.ASYNC` và `asyncSupported=true` nếu logic phải chạy ở lần dispatch sau. `OncePerRequestFilter` có `shouldNotFilterAsyncDispatch()`; default hành vi và cấu hình thực tế cần được test.
- **CompletableFuture chain:** mỗi `thenApplyAsync` trên executor khác là một thread boundary mới; propagation không "đi theo đối tượng future" một cách thần kỳ.

## 9. Dự án Spring Boot chạy được: chuyển Locale + MDC qua @Async

Demo gửi `GET /api/greeting?name=Lan` cùng `Accept-Language: vi-VN`. Controller gọi **Spring bean khác** có method `@Async("contextExecutor")`. Decorator trên executor capture **LocaleContext** và **MDC** tại thời điểm submit, khôi phục trong worker rồi restore trạng thái thread cũ.

HTTP response chứa `greeting` theo ngôn ngữ request, `locale`, `requestId` và tên worker thread để quan sát.

### 9.1. Cấu trúc

~~~text
async-context-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── AsyncContextApplication.java
    │   ├── RequestIdFilter.java
    │   ├── AsyncExecutionConfig.java
    │   ├── GreetingService.java
    │   └── GreetingController.java
    └── test/java/demo/AsyncGreetingTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-context-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Không cần Micrometer Context Propagation cho demo vì `TaskDecorator` tự triển khai copy hai loại context cụ thể. Nếu muốn đổi sang `ContextPropagatingTaskDecorator` cần bổ sung dependency và đăng ký accessor phù hợp với phiên bản framework.

### 9.3. AsyncContextApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class AsyncContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncContextApplication.class, args);
    }
}
~~~

`@EnableAsync` kích hoạt Spring async proxy. Để proxy intercept, controller phải gọi method `@Async` qua bean service được inject, không self-invocation.

### 9.4. RequestIdFilter.java

~~~java
package demo;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // Sinh ID mới, không tin header X-Request-ID tùy ý từ client.
        String id = UUID.randomUUID().toString();
        String oldId = MDC.get("requestId");

        request.setAttribute("requestId", id);
        response.setHeader("X-Request-ID", id);
        MDC.put("requestId", id);

        try {
            chain.doFilter(request, response);
        } finally {
            if (oldId == null) {
                MDC.remove("requestId");
            } else {
                MDC.put("requestId", oldId);
            }
        }
    }
}
~~~

Filter gắn requestId trên thread servlet trước khi controller gọi service. `finally` ngăn dữ liệu cũ tồn tại khi servlet thread được tái sử dụng. Đây là demo request đồng bộ trước lần ASYNC dispatch; response header tồn tại qua lifecycle của cùng HTTP response. Với cấu hình real-world cho nhiều dispatches (ERROR/ASYNC), cần test và điều chỉnh filter registration thay vì mặc định tạo ID mới ở mỗi dispatch.

### 9.5. AsyncExecutionConfig.java

~~~java
package demo;

import java.util.Map;

import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.i18n.LocaleContext;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AsyncExecutionConfig {

    @Bean("contextExecutor")
    public ThreadPoolTaskExecutor contextExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("ctx-");
        executor.setTaskDecorator(new LocaleAndMdcTaskDecorator());
        executor.initialize();
        return executor;
    }

    static final class LocaleAndMdcTaskDecorator implements TaskDecorator {
        @Override
        public Runnable decorate(Runnable delegate) {
            // Capture tại caller thread (thời điểm submit).
            LocaleContext capturedLocale =
                    LocaleContextHolder.getLocaleContext();
            Map<String, String> capturedMdc =
                    MDC.getCopyOfContextMap();

            return () -> {
                // Worker có thể từng chạy task khác: giữ trạng thái cũ.
                LocaleContext previousLocale =
                        LocaleContextHolder.getLocaleContext();
                Map<String, String> previousMdc =
                        MDC.getCopyOfContextMap();

                try {
                    if (capturedLocale == null) {
                        LocaleContextHolder.resetLocaleContext();
                    } else {
                        LocaleContextHolder.setLocaleContext(capturedLocale);
                    }

                    if (capturedMdc == null) {
                        MDC.clear();
                    } else {
                        MDC.setContextMap(capturedMdc);
                    }

                    delegate.run();
                } finally {
                    // Khôi phục trạng thái trước đó dù task lỗi.
                    if (previousLocale == null) {
                        LocaleContextHolder.resetLocaleContext();
                    } else {
                        LocaleContextHolder.setLocaleContext(previousLocale);
                    }

                    if (previousMdc == null) {
                        MDC.clear();
                    } else {
                        MDC.setContextMap(previousMdc);
                    }
                }
            };
        }
    }
}
~~~

Decorator này chỉ làm hai việc có chủ ý: truyền `LocaleContext` và map MDC. Nó **không** propagate `SecurityContext`, `ServletRequestAttributes` hay transaction. Việc copy cả map MDC phù hợp để minh họa; ứng dụng có key nhạy cảm nên lọc allowlist trước khi capture. Với thread pool, cleanup là yêu cầu bảo mật, không chỉ một vấn đề thẩm mỹ log.

Nếu số lượng tác vụ rất lớn/nhỏ, mỗi lần capture/copy map gây overhead; cân nhắc quan sát hiệu năng và dùng một thư viện propagation thống nhất nếu kiến trúc yêu cầu.

### 9.6. GreetingService.java

~~~java
package demo;

import java.util.Locale;
import java.util.concurrent.CompletableFuture;

import org.slf4j.MDC;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

record GreetingResponse(
        String greeting,
        String locale,
        String requestId,
        String workerThread) {
}

@Service
public class GreetingService {

    @Async("contextExecutor")
    public CompletableFuture<GreetingResponse> greet(String name) {
        Locale locale = LocaleContextHolder.getLocale();

        String greeting = "vi".equals(locale.getLanguage())
                ? "Xin chào, " + name
                : "Hello, " + name;

        GreetingResponse response = new GreetingResponse(
                greeting,
                locale.toLanguageTag(),
                MDC.get("requestId"),
                Thread.currentThread().getName());

        return CompletableFuture.completedFuture(response);
    }
}
~~~

Mục tiêu ở đây là quan sát Locale và MDC trong worker thread. Bản địa hóa thực tế nên dùng `MessageSource`/resource bundles thay vì toán tử ternary khi số lượng thông điệp nhiều.

Khi `@Async` interceptor điều phối lời gọi, method service chạy trên `contextExecutor`. `CompletableFuture.completedFuture(...)` được tạo **bên trong worker**, và Spring async proxy cung cấp future để controller có thể trả kết quả sau khi task hoàn tất.

### 9.7. GreetingController.java

~~~java
package demo;

import java.util.concurrent.CompletableFuture;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping(path = "/api/greeting",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public CompletableFuture<GreetingResponse> greeting(
            @RequestParam(defaultValue = "Lan") String name) {
        return service.greet(name);
    }
}
~~~

Controller nhận request trên Servlet thread, gọi Spring-managed service, nhận future và trả cho MVC. MVC xử lý async response khi future có kết quả. Không cần gọi `future.join()` trong controller: join sẽ block Servlet thread và làm mất phần lớn lợi ích của async return type.

### 9.8. Chạy và kết quả HTTP

Tại thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Gọi request tiếng Việt:

~~~bash
curl -i -G 'http://localhost:8080/api/greeting' \
  -H 'Accept-Language: vi-VN' \
  --data-urlencode 'name=Lan'
~~~

Body tương đương JSON dưới đây (request ID và tên thread có tính động):

~~~json
{
  "greeting": "Xin chào, Lan",
  "locale": "vi-VN",
  "requestId": "f64a2c8b-5e8c-4b02-9053-090122b843c4",
  "workerThread": "ctx-1"
}
~~~

HTTP response có header `X-Request-ID` với **cùng giá trị** body.requestId của request đó. Ví dụ UUID chỉ minh họa định dạng, không phải giá trị cố định. Nếu gọi với `Accept-Language: en-US`, trường `greeting` là `Hello, Lan` và `locale` là `en-US` trong cấu hình locale resolver mặc định được dùng ở demo.

### 9.9. Kiểm thử MockMvc async dispatch

Tạo file `src/test/java/demo/AsyncGreetingTest.java`:

~~~java
package demo;

import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncGreetingTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void propagatesVietnameseLocaleAndRequestId() throws Exception {
        MvcResult initial = mvc.perform(get("/api/greeting")
                .param("name", "Lan")
                .header("Accept-Language", "vi-VN"))
            .andExpect(request().asyncStarted())
            .andReturn();

        String id = initial.getResponse().getHeader("X-Request-ID");
        assertNotNull(id);
        UUID.fromString(id);

        MvcResult finalResponse = mvc.perform(asyncDispatch(initial))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode body = mapper.readTree(
                finalResponse.getResponse().getContentAsString());

        assertEquals("Xin chào, Lan", body.path("greeting").asText());
        assertEquals("vi-VN", body.path("locale").asText());
        assertEquals(id, body.path("requestId").asText());
        assertTrue(body.path("workerThread").asText().startsWith("ctx-"));
    }

    @Test
    void usesEnglishLocaleForAnotherRequest() throws Exception {
        MvcResult initial = mvc.perform(get("/api/greeting")
                .param("name", "Lan")
                .header("Accept-Language", "en-US"))
            .andExpect(request().asyncStarted())
            .andReturn();

        MvcResult finalResponse = mvc.perform(asyncDispatch(initial))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode body = mapper.readTree(
                finalResponse.getResponse().getContentAsString());
        assertEquals("Hello, Lan", body.path("greeting").asText());
        assertEquals("en-US", body.path("locale").asText());
        assertEquals(
                initial.getResponse().getHeader("X-Request-ID"),
                body.path("requestId").asText());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Hai test xác nhận HTTP MVC async lifecycle (`asyncStarted` và `asyncDispatch`), locale của từng request, mã đối chiếu từ header sang worker và tên worker. Việc chạy tuần tự hai test chưa đủ để chứng minh không có data leak trong mọi trường hợp; production cần stress test đồng thời nhiều locales/users và kiểm tra cả exception paths.

**Giới hạn demo:** Không bật Spring Security, không truyền session/ServletRequest/transaction qua worker, không kết nối database, không có distributed tracing hay message queue. Nếu tích hợp thêm các thành phần đó, phải chọn cơ chế propagation thích hợp cho chúng; TaskDecorator thủ công chỉ lo LocaleContext và MDC.

## 10. Ví dụ nguy hiểm và cách sửa

### 10.1. Sai: bắt ThreadLocal ngay trong worker

~~~java
CompletableFuture.supplyAsync(() -> {
    // Worker có thể không có Locale/RequestAttributes của HTTP request.
    return LocaleContextHolder.getLocale().toLanguageTag();
});
~~~

Cách tốt hơn khi chỉ cần ngôn ngữ:

~~~java
Locale locale = LocaleContextHolder.getLocale();
return CompletableFuture.supplyAsync(
        () -> renderMessage(locale),
        boundedExecutor);
~~~

Đây là fragment: `renderMessage` và `boundedExecutor` do ứng dụng cung cấp. Truyền `Locale` là lựa chọn đơn giản, giảm coupling với ThreadLocal. Nếu có nhiều lớp thư viện nội bộ dựa trên LocaleContextHolder, decorator/snapshot mới thực sự tiện.

### 10.2. Sai: luôn set MDC mà không clear

~~~java
executor.execute(() -> {
    MDC.put("requestId", id);
    service.run();
});
~~~

Nếu service lỗi, `requestId` có thể tồn tại trên pooled thread và lẫn sang request khác. Dùng `finally` restore MDC hoặc executor TaskDecorator đã kiểm thử.

### 10.3. Sai: tạo thêm thread thủ công mỗi request

~~~java
new Thread(() -> expensiveWork()).start();
~~~

Cách này bỏ qua pool management, shutdown, queue, context, error visibility và rate limits. Dùng executor được quản lý, backpressure và timeout rõ ràng; với công việc lâu/durable dùng queue/job system.

### 10.4. Sai: giữ HttpServletRequest trong background job dài

~~~java
executor.execute(() ->
        saveAuditRecord(request.getHeader("Authorization")));
~~~

Đoạn này vừa giữ reference request quá vòng đời cần thiết, vừa chuyển bearer token vào job/log. Nếu audit cần danh tính đã được kiểm tra, chuẩn bị một `AuditActorId` hoặc context đã được phép trên request thread rồi đưa vào task.

### 10.5. Sai: copy transaction bằng ThreadLocal

Một transaction gắn với connection và tài nguyên nhất định. Copy `TransactionSynchronizationManager` sang thread khác không phải cách chia sẻ transaction an toàn. Hãy mở transaction trên worker/service với `@Transactional` ở đúng proxy boundary khi nghiệp vụ cần, hoặc đổi thiết kế để chỉ có một transaction boundary.

### 10.6. Sai: coi CompletableFuture luôn non-blocking I/O

`CompletableFuture.supplyAsync(() -> jdbcRepository.findAll(), executor)` giải phóng Servlet thread trong khi worker chờ JDBC, nhưng I/O JDBC đó **vẫn blocking trên worker thread**. Nếu tải cao, worker pool vẫn có thể cạn. Cần chọn pool sizing, query timeout và kiến trúc phù hợp thay vì chỉ thêm `@Async`.

## 11. Checklist debug khi ngữ cảnh biến mất

1. **Xác định thread boundary:** controller → @Async service? common pool? thenApplyAsync? scheduled callback? HTTP client?
2. **Kiểm tra capture ở đâu:** caller thread có locale, MDC, SecurityContext đúng vào lúc submit không?
3. **Kiểm tra executor thật:** @Async có đúng bean `contextExecutor`? Có bị self-invocation bỏ qua proxy không?
4. **Kiểm tra decorator/wrapper:** được gắn lên executor thực thi task chưa? Có accessor đúng nếu dùng Micrometer không?
5. **Kiểm tra cleanup:** có finally restore trạng thái cũ khi lỗi, timeout hoặc cancellation không?
6. **Kiểm tra duration:** task có tiếp tục sau HTTP request/session kết thúc? Có đang giữ ServletRequestAttributes quá lâu?
7. **Kiểm tra security:** có truyền Authentication không phù hợp? Có cần re-authorize vào thời điểm job chạy?
8. **Kiểm tra locale:** header Accept-Language có được locale resolver chấp nhận? default locale có đang che lỗi propagation?
9. **Kiểm tra tracing:** đã có tracing library tự động propagate chưa? Có nhiều wrappers ghi đè context?
10. **Kiểm tra production:** bounded thread pool, queue capacity, rejection, error handler, timeout, data retention và multi-node.
11. **Kiểm tra test:** một request vi-VN, một request en-US, chạy concurrent, assert MDC requestId không bị lẫn; test error path.
12. **Kiểm tra MVC dispatch:** filter/interceptor có chạy trên ASYNC dispatch theo yêu cầu không? Tránh tạo request ID mới ở lần dispatch sau.

Một lỗi phổ biến trong test là **nhìn thấy đúng locale mặc định rồi tưởng propagation hoạt động**. Hãy test hai ngôn ngữ khác nhau, cấu hình locale resolver rõ và xác minh worker thread thực sự khác thread ban đầu.

## 12. Tình huống mở rộng

### 12.1. Async gửi email sau khi HTTP trả 202 Accepted

API nhận yêu cầu và trả 202, job gửi email tiếp tục trong queue. Không nên giữ `LocaleContextHolder` hay HTTP session để dựa vào thời điểm gửi email có thể xảy ra muộn. Thay vào đó tạo job payload:

~~~java
record EmailJob(
        String templateId,
        String recipientId,
        String languageTag,
        String businessCorrelationId) {}
~~~

Worker tái tạo `Locale.forLanguageTag(languageTag)` và kiểm tra business context cần thiết trước khi gửi. Nếu có thay đổi ngôn ngữ người dùng giữa lúc enqueue và lúc thực hiện, chính sách phải xác định dùng snapshot lúc enqueue hay ưu tiên ngôn ngữ mới.

### 12.2. Worker dùng thời gian theo vùng

Cần cả `ZoneId` và locale, ví dụ người dùng ở Việt Nam:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime time = instant.atZone(zone);
~~~

Cần imports từ `java.util` và `java.time`; biến `instant` phải là một `Instant` đã xác định. Locale kiểm soát ngôn ngữ/format, ZoneId kiểm soát quy tắc giờ; truyền nhầm một cái không thay thế cái kia.

### 12.3. Nhiều task phụ thuộc nhau

Với `CompletableFuture`, một callback `thenApply` không hậu tố Async có thể chạy trên thread hoàn thành stage trước, không chắc là request thread. Callback `thenApplyAsync` có thể chạy ở common pool nếu không cấp executor. Mỗi stage sử dụng thông tin context cần contract rõ; không nên dựa vào "thread tình cờ" đã có đúng giá trị.

### 12.4. Logging trên async callback

Nếu chỉ cần request ID để đối chiếu log, việc truyền nó như giá trị:

~~~java
String id = MDC.get("requestId");
executor.execute(() -> {
    try (MDC.MDCCloseable ignored =
            MDC.putCloseable("requestId", id)) {
        service.run();
    }
});
~~~

là một phương án đơn giản khi bạn kiểm soát một callback cụ thể. Chú ý `MDC.putCloseable` sẽ remove key khi scope kết thúc, không đảm bảo restore giá trị trước nếu worker đang có key đó; với nested context hãy dùng snapshot-and-restore đầy đủ như TaskDecorator ở mục 9. Không đưa bí mật vào key ID.

## 13. Bài tập tự kiểm tra

**Bài 1 — ThreadLocal cơ bản:** Đọc lại chương trình ở mục 2 và giải thích vì sao stdout đầu tiên là `true`. Bỏ finally trong wrapped task và mô tả rủi ro khi worker được tái sử dụng.

**Bài 2 — Localization:** Một request `Accept-Language: vi-VN` gọi `CompletableFuture.supplyAsync()` và service in English. Hãy xác định chỗ locale mất và sửa bằng cách truyền `Locale` vào lambda thay vì đọc ThreadLocal trong worker.

**Bài 3 — MDC:** Viết TaskDecorator capture `requestId` khi submit và restore previous value sau task. Tạo 100 requests song song với hai locales khác nhau; kiểm tra id không bị lẫn giữa responses.

**Bài 4 — Security:** So sánh copy SecurityContext vào task ngắn với job nền chạy sau 10 giờ. Vì sao job lâu nên lưu user/tenant ID và kiểm tra quyền theo chính sách riêng?

**Bài 5 — Spring MVC:** Phân biệt `Callable<T>`, `DeferredResult<T>`, controller trả `CompletableFuture<T>` và service `@Async`. Ai tạo worker, ai giữ HTTP response đang chờ, và async dispatch xuất hiện ở đâu?

**Bài 6 — Timezone:** Một locale `en-US` không đủ xác định múi giờ. Thiết kế `DisplayContext(Locale, ZoneId)` dùng để format một `Instant` trên worker.

**Bài 7 — Micrometer:** Nêu điều kiện để `ContextSnapshot.captureAll()` biết cách chụp `LocaleContextHolder`, và vì sao không nên propagate `ServletRequestAttributes` của request đã kết thúc.

**Bài 8 — CompletableFuture:** Có chuỗi `supplyAsync(..., executorA).thenApplyAsync(..., executorB)`. Vì sao context có thể đúng ở A nhưng mất ở B? Đề xuất decorator cho cả hai hoặc truyền explicit context.

**Bài 9 — Kiểm thử:** Viết MockMvc test cho hai requests Accept-Language khác nhau, dùng `asyncDispatch` và assert request ID từ header khớp trường JSON worker đã trả.

**Bài 10 — Vận hành:** Đề xuất metrics/alerting khi pool queue đầy, task timeout, rejection và tỷ lệ lỗi 5xx tăng. Vì sao không nên retry vô hạn POST không idempotent?

## 14. Ghi nhớ

- Context **gắn với ThreadLocal** không tự theo thread mới. Propagation phải có chủ đích ở mỗi boundary.
- `LocaleContextHolder` xử lý ngôn ngữ; `RequestContextHolder` gắn request; `MDC` dành cho logging; `SecurityContextHolder` thuộc bảo mật. Chúng không thể hoán đổi tùy tiện.
- Ưu tiên **truyền immutable business context tường minh** cho background job, nhất là công việc tiếp tục sau HTTP request.
- Với `@Async` và ThreadPoolTaskExecutor, dùng `TaskDecorator` **capture on submit, install on worker, restore in finally**.
- Micrometer Context Propagation và Spring Security executors hỗ trợ propagation có điều kiện; chọn đúng dependency, accessor, executor và lifetime.
- MVC async return types vẫn trải qua Servlet async/ASYNC dispatch. Không tự động coi `@Async` là non-blocking I/O hoặc bảo đảm mọi context được truyền.
- Test nhiều locales/requests đồng thời và exception paths; tránh stale context, rò dữ liệu và lỗi bảo mật.

## 15. Tài liệu chính thức

- [Spring Framework 6.2 — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): Callable, DeferredResult, CompletionStage, async processing, context propagation, executor configuration.
- [Spring Framework 6.2 — TaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/TaskDecorator.html): interface cho task context wrapping.
- [Spring Framework 6.2 — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): Micrometer context propagation trong executors.
- [Spring Framework 6.2 — LocaleContextHolder](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/i18n/LocaleContextHolder.html): locale context theo thread.
- [Spring Framework 6.2 — RequestContextHolder](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html): request attributes theo thread.
- [Spring Security 6.5 — Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html): DelegatingSecurityContextRunnable/Executor và Spring task executors.
- [Micrometer — Context Propagation](https://docs.micrometer.io/context-propagation/reference/): ThreadLocalAccessor, ContextRegistry và ContextSnapshot.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): traceparent/tracestate khi cần propagate distributed trace qua HTTP.
