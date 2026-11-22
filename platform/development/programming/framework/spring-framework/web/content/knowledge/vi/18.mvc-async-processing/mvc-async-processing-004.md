# Luồng dispatch ASYNC và xử lý kết quả hoặc ngoại lệ trong Spring MVC

## 1. Mục tiêu: hiểu đúng hai lượt xử lý một HTTP request

Trong ứng dụng Servlet truyền thống, một HTTP request thường chiếm một servlet container thread cho tới khi controller trả kết quả và response hoàn tất. Nhưng một số công việc phải đợi I/O, event từ hệ thống khác hoặc tác vụ lâu hơn bình thường. Spring MVC có **Servlet asynchronous request processing**: trả lại servlet thread trước khi có kết quả, giữ HTTP response mở, rồi tiếp tục xử lý khi kết quả sẵn sàng.

Ví dụ endpoint dùng `Callable`:

~~~java
@GetMapping("/report")
public Callable<ResponseEntity<String>> report() {
    return () -> ResponseEntity.ok("ready");
}
~~~

Khi controller **trả về đối tượng `Callable`**, chuỗi `"ready"` **chưa phải** HTTP response cuối tại thời điểm đó. Spring MVC:
1. Đưa request vào asynchronous mode qua Servlet async API.
2. Chạy `Callable` trên `AsyncTaskExecutor`.
3. Cho servlet container thread đang phục vụ request trở lại pool trong lúc chờ.
4. Khi task xong, **dispatch request lần nữa với `DispatcherType.ASYNC`**.
5. `DispatcherServlet` xử lý **kết quả đã được lưu**, không gọi lại method controller để chạy lại task.
6. Resolve return value hoặc exception, ghi response và kết thúc async request.

**Quan trọng:** một HTTP request có thể có nhiều pha/dispatch nội bộ, nhưng client vẫn thấy **một HTTP response**. `ASYNC` là loại Servlet dispatch; nó **không** có nghĩa client gửi một HTTP method `ASYNC`.

### Sau bài này, bạn sẽ làm được

- Vẽ thứ tự `REQUEST` → `startAsync` → worker/event → `ASYNC` → response.
- Phân biệt Servlet container thread với thread xử lý `Callable` hoặc nơi gọi `DeferredResult.setResult`.
- Dùng đúng `Callable<T>`, `DeferredResult<T>` và `WebAsyncTask<T>` cho một kết quả bất đồng bộ.
- Hiểu kết quả thành công và lỗi đi qua `HandlerMethodReturnValueHandler`, `HttpMessageConverter`, `HandlerExceptionResolver` / `@ExceptionHandler`.
- Phân biệt exception từ worker với timeout, client disconnect và exception sau khi response đã commit.
- Hiểu `AsyncHandlerInterceptor`, filter dispatcher types, Spring Security context, cleanup và cấu hình executor/timeout.
- Viết ví dụ Java 17+ Spring Boot 3.3.5 và MockMvc với `request().asyncStarted()`, `asyncDispatch(...)` và assertions HTTP cuối.
- Biết điểm khác giữa MVC async, Java `@Async` và Spring WebFlux/reactive processing.

Bài tập trung **Spring MVC Servlet stack**; không diễn giải cơ chế này như WebFlux. Các tên API minh họa phù hợp Spring Framework 6.1.x trong Spring Boot 3.3.5.

## 2. Vì sao trả `Callable` không đồng nghĩa trả response ngay?

Nhìn vào hai controller:

~~~java
@GetMapping("/sync")
public String sync() {
    return slowService.load();
}

@GetMapping("/async")
public Callable<String> async() {
    return () -> slowService.load();
}
~~~

Đây là hai fragments minh họa (chưa có class và bean `slowService`). `sync` chờ `load()` hoàn thành trên servlet request thread. `async` giao việc cho executor; servlet thread có thể quay lại phục vụ request khác khi tác vụ đang chạy.

Tuy nhiên, **tác vụ I/O bên trong Callable vẫn có thể blocking** và chiếm một **worker thread**. MVC async không làm JDBC/HTTP blocking call tự trở thành non-blocking. Lợi ích là tránh chiếm container threads trong thời gian đợi; chi phí là thread pool, queue, context propagation và một lượt dispatch nữa.

Nếu gọi `Thread.sleep` hoặc REST client đồng bộ 10 giây trong Callable, bạn vẫn dùng một thread ở executor trong 10 giây. Chỉ thay nơi chờ, không “loại bỏ” thời gian chờ. Với hiệu năng, cần đo số threads, hàng đợi và latency trước/sau.

## 3. Chu trình Servlet: `REQUEST`, async mode và `ASYNC`

### 3.1. Sơ đồ theo các giai đoạn

~~~text
Client           Servlet container          Spring MVC             Async executor/event
  |                      |                       |                          |
  | GET /api/async/...   |                       |                          |
  |--------------------->|  DispatcherType.REQUEST                         |
  |                      |-- Filters ---------->|                          |
  |                      |                       | HandlerMapping            |
  |                      |                       | Controller returns        |
  |                      |                       | Callable/DeferredResult  |
  |                      |                       | startAsync()             |
  |                      |                       |------------------------->| Callable worker
  |                      |<-- Filter/Servlet exit|                          |
  |                      |  request thread free  |                          |
  |                      |  response remains open|                          |
  |                      |                       |                 compute result
  |                      |<-----------------------------------------------  |
  |                      |  async dispatch       |                          |
  |                      |  DispatcherType.ASYNC |                          |
  |                      |-- Filters* ---------->| DispatcherServlet again |
  |                      |                       | consume saved result     |
  |                      |                       | serialize OR resolve err |
  |<---------------------| response completes    |                          |
~~~

Dấu `Filters*` nhắc rằng **chỉ những filters được map cho dispatcher type `ASYNC`** và phù hợp quy tắc dispatch mới tham gia lượt sau. Một `OncePerRequestFilter` còn có logic nên bỏ qua async dispatch hay không. Đừng giả định mọi filter sẽ chạy hai lần, hoặc không filter nào chạy lần thứ hai.

### 3.2. Servlet API bên dưới

Ở mức Servlet, `HttpServletRequest.startAsync()` trả về `AsyncContext` và đặt request ở chế độ async (nếu servlet/filter chain cho phép). Tác dụng chính:
- Servlet có thể kết thúc lần dispatch ban đầu.
- Response vẫn còn mở cho kết quả sau.
- Ứng dụng/container có thể dispatch lại hoặc complete.
- Async request có thể timeout và nhận notifications `AsyncListener`.

Spring MVC quản lý những thao tác này thông qua tầng hạ tầng như `WebAsyncManager`, `AsyncWebRequest` và argument/return-value processing. **Không tự gọi `request.startAsync()` trong controller đã trả `Callable`/`DeferredResult`**: nếu trộn hai cách quản lý độc lập, dễ phát sinh double-dispatch, race condition hoặc response chưa hoàn tất.

### 3.3. Một request hay hai request?

Có **một** request HTTP từ client. Trong server, có hai lần Servlet dispatch:
- `REQUEST`: nhận request, chọn handler, controller trả async handle.
- `ASYNC`: tiếp tục sau khi có kết quả hoặc lỗi.

Khi dispatch ASYNC, Spring MVC vẫn tìm được handler mapping tương ứng để tiếp tục pipeline, nhưng **không gọi lại controller method**; kết quả đã được `WebAsyncManager` lưu để return-value/exception resolvers xử lý. Vì vậy không ghi nghiệp vụ vào một MVC interceptor `preHandle` với giả định nó chỉ chạy đúng một lần mỗi request: cần xét async redispatch.

### 3.4. Phân biệt Servlet dispatch và HTTP redirect/forward

| Cơ chế | Client có gửi request mới? | Ý nghĩa |
| --- | --- | --- |
| `DispatcherType.REQUEST` | Client gửi request ban đầu | Xử lý HTTP request bình thường |
| `DispatcherType.ASYNC` | Không | Container tiếp tục cùng logical HTTP request sau async completion |
| `DispatcherType.FORWARD` | Không phải request HTTP mới | Servlet forward nội bộ |
| HTTP `302 Location` | Browser/client thường gửi request mới khi follow redirect | Một HTTP round-trip khác |
| `DispatcherType.ERROR` | Không nhất thiết | Error dispatch của container theo cấu hình |

`ASYNC` dispatch không phải một redirect, không phải server push và không phải message queue acknowledgement. Nếu muốn client quay lại hỏi trạng thái, đó là thiết kế **202 Accepted + status endpoint** khác, không phải nội bộ MVC async dispatch.

## 4. `Callable<T>`: Spring quản lý worker và resume kết quả

### 4.1. Luồng xử lý chính

Khi handler trả `Callable<T>`, Spring:
1. Chấp nhận return value là một asynchronous computation.
2. Đưa request vào async mode.
3. Submit `Callable` vào `AsyncTaskExecutor` do MVC cấu hình.
4. Cho `DispatcherServlet` và những filters trong lượt ban đầu thoát.
5. Worker chạy `Callable.call()` và thu kết quả hoặc `Throwable`.
6. Lưu kết quả trong async manager, yêu cầu container dispatch ASYNC.
7. Với result, xử lý return value giống controller trả đối tượng đó trực tiếp.
8. Với exception, đi qua Spring MVC exception handling.

Ví dụ:

~~~java
@GetMapping("/callable")
public Callable<ResponseEntity<String>> callable() {
    return () -> ResponseEntity.ok("worker complete");
}
~~~

Spring MVC có thể serialize `"worker complete"` thành response sau dispatch. **ResponseEntity không được ghi hoàn tất ngay khi controller trả Callable**.

### 4.2. Kết quả không phụ thuộc định danh thread

Có thể thấy ba thread khác nhau:
- `T1`: container thread xử lý REQUEST.
- `T2`: executor worker chạy Callable.
- `T3`: container thread xử lý ASYNC.

Không yêu cầu T1 ≠ T3 trong mọi runtime: thread pool có thể tái sử dụng cùng thread. Bản chất là **ngữ cảnh dispatch được chia theo pha**, không phải nhất thiết phải có ba tên thread khác nhau. Không dùng thread name/order làm API contract hoặc assertion cứng.

### 4.3. Callable ném exception ở thread khác có bị mất không?

Không, nếu exception xảy ra **bên trong Callable do Spring MVC quản lý**, Spring giữ nó như kết quả async và dispatch lần nữa. Ở lượt ASYNC, nó đi qua `HandlerExceptionResolver` và `@ExceptionHandler` tương tự exception trong synchronous controller.

~~~java
@GetMapping("/callable/fail")
public Callable<String> fail() {
    return () -> {
        throw new IllegalStateException("simulated");
    };
}
~~~

Đây là fragment chỉ để diễn giải; code production không nên để `IllegalStateException` nội bộ lộ nguyên văn tới client. Một `@RestControllerAdvice` map exception public đã biết sang status/body an toàn; lỗi không đoán trước trở thành 500 và được log bảo vệ phía server.

### 4.4. Khác với tạo thread thủ công

Không viết:

~~~java
@GetMapping("/bad")
public String bad() {
    new Thread(() -> expensiveWork()).start();
    return "done";
}
~~~

Code trên **trả HTTP response trước khi biết công việc thành công hay thất bại**, không phải MVC async response. Nó còn tạo thread không kiểm soát và làm exception rơi vào một nơi khác. Nếu mục tiêu là job dài thực sự, dùng task queue/job table và endpoint trả 202 + job ID, không giữ HTTP connection mở vô hạn.

## 5. `DeferredResult<T>`: một kết quả đến từ nguồn bên ngoài

Với `Callable`, Spring MVC biết computation để submit. Với `DeferredResult`, controller trả một **holder** cho kết quả sẽ được thiết lập sau bởi ứng dụng: message listener, callback từ service, completion của workflow, scheduler hoặc một worker do bạn điều phối.

~~~java
@GetMapping("/deferred")
public DeferredResult<String> deferred() {
    DeferredResult<String> result = new DeferredResult<>(5_000L);

    // Nguồn ngoài hoặc executor sẽ gọi sau:
    scheduleCallback(() -> result.setResult("event arrived"));

    return result;
}
~~~

`scheduleCallback` là tên hàm minh họa, không nằm trong Servlet/Spring API. Ví dụ đầy đủ có executor thật ở mục 10.

### 5.1. Khi gọi `setResult(...)`

Nếu gọi:

~~~java
boolean accepted = result.setResult(ResponseEntity.ok(body));
~~~

Spring lưu giá trị nếu kết quả chưa được quyết định, sau đó thực hiện async dispatch để xử lý nó như return value bình thường của handler. Phương thức trả boolean để biểu thị có chấp nhận thiết lập kết quả đó hay không; **không suy ra response đã gửi thành công cho browser**. Kết quả có thể bị từ chối nếu request đã timeout/completed hoặc một result khác thắng race.

### 5.2. Khi gọi `setErrorResult(...)`

~~~java
result.setErrorResult(new ResourceNotFoundException("record missing"));
~~~

Nếu object là exception phù hợp, lượt ASYNC xử lý nó qua exception resolvers. `setErrorResult` cũng có thể nhận non-exception Object làm alternate result theo contract của Spring, nhưng nên dùng exception/domain result rõ ràng, tránh nhầm lẫn với response thành công.

**Một exception ném trong `Runnable` riêng nhưng không gọi `setErrorResult` sẽ không tự động trở thành lỗi của request.** Ví dụ:

~~~java
executor.execute(() -> {
    throw new RuntimeException("lost to request");
});
~~~

Nếu handler đã trả `DeferredResult`, exception của runnable này không được MVC liên kết tự động với holder. Cần bắt exception trong callback rồi gọi `setErrorResult`:

~~~java
executor.execute(() -> {
    try {
        String data = externalService.load();
        result.setResult(data);
    } catch (Exception ex) {
        result.setErrorResult(ex);
    }
});
~~~

Các dòng trên là fragment có biến executor/service/result; demo đầy đủ sử dụng nó ở dưới. Phân biệt này là **nguyên nhân phổ biến khiến request DeferredResult treo đến timeout trong khi worker logs đã báo lỗi**.

### 5.3. Timeout và completion callbacks

`DeferredResult` cung cấp:
- `onTimeout(Runnable)`: callback khi async request timeout.
- `onError(Consumer<Throwable>)`: callback khi có lỗi ở request/async processing.
- `onCompletion(Runnable)`: callback khi async lifecycle kết thúc, dù thành công/thất bại.

Một timeout callback có thể cố `setErrorResult(...)` hoặc chọn alternate result; nhưng callbacks có race với producer. Sau completion, nên dọn registry/pending entries, hủy đăng ký listener và tránh memory leaks. **Không dùng `onCompletion` như bằng chứng business transaction thành công**.

## 6. `WebAsyncTask<T>`: Callable với timeout/executor tùy biến

`WebAsyncTask<T>` bọc `Callable<T>` và cho phép timeout, executor riêng, xử lý timeout/error/completion.

~~~java
@GetMapping("/web-task")
public WebAsyncTask<ResponseEntity<String>> webTask() {
    WebAsyncTask<ResponseEntity<String>> task =
            new WebAsyncTask<>(3_000L,
                    () -> ResponseEntity.ok("task done"));

    task.onTimeout(() -> ResponseEntity.status(503).body("timed out"));
    task.onCompletion(() -> {
        // Tài nguyên gắn với request có thể được dọn tại đây.
    });
    return task;
}
~~~

Đoạn fragment minh họa, cần các imports Spring. `3_000L` trong constructor là **milliseconds**. Callback timeout chạy trong container thread và phải xử lý rất nhanh, **không ngủ/chờ network** trong callback.

`WebAsyncTask.onError(Callable<T>)` cũng có thể cung cấp alternate result cho lỗi trong async request processing. Không nhầm `onError` này với mọi exception ném **bên trong worker Callable**: exception từ worker thường được Spring đưa thẳng qua MVC exception handling; thiết kế handler theo loại lỗi thực tế.

Timeout trên `WebAsyncTask` không phải guarantee cho việc chủ động dừng một JDBC query, HTTP request hay thread đang block. Cần per-dependency timeouts, cancellation/cooperative interrupt và bounded resources khi sử dụng thực.

## 7. Lượt `ASYNC` dispatch xử lý kết quả như thế nào?

### 7.1. Trường hợp thành công

~~~text
T1: DispatcherServlet --> Controller returns Callable<Payload>
T1: Spring starts async; servlet/filter chain exits
T2: Callable returns Payload
T2: WebAsyncManager stores result; asks AsyncContext.dispatch()
T3: DispatcherServlet on ASYNC
T3: stored Payload --> return value handling --> HttpMessageConverter
T3: response status/headers/body; complete
~~~

Nếu `Payload` là Java record và controller `@RestController`, JSON converter (thường Jackson) serialize nó tại lượt xử lý result. Với `ResponseEntity<Payload>`, status và headers bên trong object được MVC dùng ở pha hoàn tất.

### 7.2. Trường hợp exception

~~~text
T1: Controller returns Callable
T2: Callable throws ResourceNotFoundException
T2: Spring saves exception as async result
T3: ASYNC dispatch
T3: HandlerExceptionResolver / @RestControllerAdvice
T3: HTTP 404 + safe ProblemDetail JSON
~~~

Đối với `DeferredResult`:

~~~text
T1: Controller returns DeferredResult
E1: External callback calls setErrorResult(exception)
T3: ASYNC dispatch
T3: @ExceptionHandler can map the exception
~~~

Điểm mấu chốt là **exception phải được đưa vào quy trình Spring MVC**. Nếu bạn tạo một thread tùy ý rồi exception bị uncaught, MVC không thể biết nên gửi 404/500 cho request cụ thể nào. Hãy kết nối qua `setErrorResult` hoặc một loại return value mà Spring hiểu.

### 7.3. Sự tham gia của `@RestControllerAdvice`

`@ExceptionHandler` trong controller hoặc `@RestControllerAdvice` vẫn có thể áp dụng sau ASYNC dispatch. Nếu handler chỉ trả 500 default cho exception chưa biết, đừng đưa stack trace, raw SQL message, token hay path server vào response. Với một exception nghiệp vụ public, đặt `code` máy đọc được và HTTP status phù hợp.

Spring MVC 6.x còn có `ProblemDetail`/`ErrorResponse` và `ResponseEntityExceptionHandler`. Khi kế thừa `ResponseEntityExceptionHandler`, hãy override hooks dành cho built-in exceptions thay vì thêm @ExceptionHandler trùng loại với superclass, tránh ambiguous mapping.

### 7.4. Sau khi response đã commit

Nếu đã stream bytes xuống client, server **không còn tự do đổi HTTP status/body** như trước. `ResponseBodyEmitter`/`SseEmitter` có cơ chế complete/error riêng; lỗi I/O do client disconnect không phải lúc nào cũng gửi được một body 500 đẹp. Bài này tập trung **một kết quả async** qua Callable/DeferredResult/WebAsyncTask, không tự hứa advice xử lý được mọi lỗi xảy ra sau khi body đã gửi.

## 8. Timeout, lỗi, client disconnect và race conditions

### 8.1. Timeout mặc định

Không tự đoán timeout là “mặc định 30 giây” trong mọi deployment. Default Servlet async timeout phụ thuộc container/configuration và có thể được Spring MVC tùy chỉnh. Với `WebMvcConfigurer.configureAsyncSupport`:

~~~java
@Override
public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
    configurer.setDefaultTimeout(10_000L);
}
~~~

Đơn vị là milliseconds. `DeferredResult<>(5_000L)` hoặc `WebAsyncTask<>(3_000L, callable)` có thể đặt timeout riêng cho request; một số load balancer/gateway/client timeout còn ngắn hơn. Hiệu lực timeout của API phụ thuộc **nhiều tầng**, không chỉ Spring.

### 8.2. Nếu timeout mà không có handler tùy chỉnh

Spring có `AsyncRequestTimeoutException`, mặc định thường dẫn tới **503 Service Unavailable** qua MVC exception infrastructure trong Spring 6.1. Một callback timeout tùy biến có thể quyết định result/status khác, ví dụ 504 cho gateway-like use case nếu đúng semantics. Đừng khẳng định mọi timeout chắc chắn 504.

Dựa vào `@RestControllerAdvice` và `onTimeout` để tạo error schema ổn định; phải test thực tế và tránh trả 200 với body mô tả lỗi nếu client cần status hợp lệ.

### 8.3. Producer thắng hay timeout thắng?

Giả sử executor vừa hoàn thành khi timeout xảy ra:

~~~text
T2: result.setResult(payload)        ↘
                                      một kết quả được chấp nhận
T3: timeout callback setErrorResult ↗
~~~

`DeferredResult` giúp điều phối một terminal result, nhưng callback ngoài vẫn có thể đang chạy hoặc chuẩn bị làm side effect. Kiểm giá trị boolean trả về của `setResult`/`setErrorResult` khi cần instrumentation, dọn pending work, không ghi business event “gửi thành công” chỉ dựa vào điều đó.

### 8.4. Client đã đóng kết nối

Servlet async nói chung không có một sự kiện “client đóng tab” luôn được gửi ngay và chính xác theo mọi trường hợp. Với streaming, write có thể ném `IOException` khi có lỗi kết nối; đối với single result, server đôi lúc chỉ phát hiện khi serialize/write cuối. Đừng giữ work vô hạn dựa trên hy vọng client luôn kết nối.

Nên có bounded timeout ở service, HTTP client/database và queue; cancellation khi có thể; cleanup trong completion callback; idempotency cho side effects. Không trả thông tin nhạy cảm trong error log lúc client disconnect.

### 8.5. Executor bị đầy

Async MVC giải phóng container thread nhưng **không miễn phí năng lực thực thi**. Nếu pool có 8 threads nhưng liên tục nhận hàng nghìn tasks blocking, queue sẽ lớn, latency tăng và request timeout. Có thể dẫn đến task rejection khi vượt ngưỡng.

Dùng bounded executor, overload policy, metrics, per-dependency timeout và backpressure/admission control ở app/gateway. Không dùng pool vô hạn trong production; không tạo một thread mới cho mỗi request.

## 9. `AsyncHandlerInterceptor` và các callback của MVC

`HandlerInterceptor` bình thường có `preHandle`, `postHandle` và `afterCompletion`. Khi controller bắt đầu async:
- Ở **REQUEST ban đầu**, `preHandle` thường chạy.
- Khi concurrent handling bắt đầu, một `AsyncHandlerInterceptor` nhận `afterConcurrentHandlingStarted` **thay cho** `postHandle` và `afterCompletion` trong lượt đầu.
- Ở **ASYNC dispatch**, interceptor có thể đi qua lifecycle thêm lần nữa; `preHandle` có thể được gọi lại rồi `postHandle/afterCompletion` chạy khi hoàn tất tùy đường xử lý.

Ví dụ fragment:

~~~java
public final class TraceAsyncInterceptor implements AsyncHandlerInterceptor {

    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request, HttpServletResponse response,
            Object handler) {
        // Dọn ThreadLocal của REQUEST thread nếu cần.
    }
}
~~~

Fragment này cần imports `AsyncHandlerInterceptor` và Servlet types; không đăng ký vào demo runnable vì không cần thay request ở ví dụ chính.

**Lỗi thường gặp:** code bắt đầu timer trong `preHandle` và tăng pageview trong đó, sau ASYNC redispatch lại tăng thêm lần nữa. Nếu business side effect chỉ được phép chạy một lần, cần đánh dấu trên request scope/kiểm dispatcher type hoặc đặt side effect tại nơi phù hợp, không tin interceptor luôn gọi đúng một lần.

### 9.1. Filters và `DispatcherType.ASYNC`

Servlet filters có mapping dispatcher types; trong Boot, khi đăng ký `FilterRegistrationBean` có thể chỉ rõ:

~~~java
registration.setDispatcherTypes(
        DispatcherType.REQUEST, DispatcherType.ASYNC);
registration.setAsyncSupported(true);
~~~

Đây là fragment cần `registration` và import `jakarta.servlet.DispatcherType`. Nếu servlet/filter không hỗ trợ async, runtime có thể gặp `IllegalStateException` khi bắt đầu asynchronous processing.

Với `OncePerRequestFilter`, xem `shouldNotFilterAsyncDispatch()` và `isAsyncDispatch(request)`; nó có cơ chế tránh chạy nhiều lần tùy dispatcher type và override. Không mặc định tự gọi filter custom trên mọi ASYNC dispatch chỉ vì class có tên “Once”.

### 9.2. Filter chain và Spring Security

Spring Security có tích hợp `WebAsyncManagerIntegrationFilter` giúp xử lý `SecurityContext` khi dùng Spring MVC `Callable`. Tuy vậy, **custom threads**, `DeferredResult` được hoàn thành từ message listener và nhiều `CompletableFuture` callbacks **không tự luôn có cùng `SecurityContextHolder`**, MDC hoặc transaction context như container request thread.

Nếu worker cần principal/tenant, nên capture **immutable, đã xác thực** data từ controller/service và truyền qua parameter an toàn, hoặc dùng `DelegatingSecurityContextExecutor`/context propagation theo framework/config cụ thể. Không giữ nguyên đối tượng mutable `HttpServletRequest` trong worker để đọc user/session ở thời điểm tùy ý. Không tự assume `@Transactional` context sẽ đi theo thread khác; transaction thường thread-bound và cần ranh giới service được gọi đúng trong worker.

### 9.3. MDC, tracing và correlation

`ThreadLocal`/SLF4J MDC thường không tự lan qua thread pools. Nếu log theo trace/request ID, dùng tracing context propagation hoặc task decorator phù hợp, đảm bảo clear context cuối task để tránh dữ liệu request này còn lại trên thread tái sử dụng ở request khác.

Không đưa raw cookies/Authorization header/token vào logs để “sửa async”. Một trace ID vô hại và task ID riêng giúp liên kết T1/T2/T3 tốt hơn log tên thread.

## 10. Ví dụ chạy được: Spring Boot 3.3.5, Callable, DeferredResult, WebAsyncTask

Demo minh họa một kết quả async có thể là **thành công**, **không tìm thấy** hoặc **timeout**:
- `GET /api/async/callable/{id}`: `Callable<ResponseEntity<Payload>>` được chạy trên MVC executor.
- `GET /api/async/deferred/{id}`: `DeferredResult<ResponseEntity<Payload>>` được kết thúc bằng executor callback; khi lỗi gọi `setErrorResult`.
- `GET /api/async/web-task/{id}`: `WebAsyncTask<ResponseEntity<Payload>>` có timeout riêng.
- `@RestControllerAdvice`: map `MissingItemException` sang 404 và `WorkTimedOutException` sang 503 bằng `ProblemDetail`.
- MockMvc: assert `asyncStarted`, gọi `asyncDispatch` rồi kiểm response cuối.

Không có database, Spring Security hoặc network client thực; kết quả là **fixture deterministic**, không tuyên bố worker thật sự làm I/O lâu. Mục tiêu là mô tả lifecycle và exception propagation. Test không cố gây timeout bằng `Thread.sleep` vì sẽ khiến CI flaky.

~~~text
mvc-async-dispatch-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/mvcasync/
    │   ├── AsyncApplication.java
    │   ├── config/AsyncMvcConfig.java
    │   └── web/
    │       ├── AsyncController.java
    │       ├── AsyncErrorAdvice.java
    │       ├── MissingItemException.java
    │       └── WorkTimedOutException.java
    └── test/java/com/example/mvcasync/web/
        └── AsyncControllerTest.java
~~~

### 10.1. Gradle build

`settings.gradle`:

~~~groovy
rootProject.name = 'mvc-async-dispatch-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` cung cấp Spring MVC, Servlet container (Tomcat mặc định với Boot starter Web) và JSON converter Jackson. `spring-boot-starter-test` cung cấp JUnit 5, MockMvc. Không cần `spring-boot-starter-webflux` chỉ để dùng Callable/DeferredResult của MVC.

### 10.2. Main class

`src/main/java/com/example/mvcasync/AsyncApplication.java`:

~~~java
package com.example.mvcasync;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncApplication.class, args);
    }
}
~~~

### 10.3. Cấu hình executor có giới hạn và MVC timeout

`src/main/java/com/example/mvcasync/config/AsyncMvcConfig.java`:

~~~java
package com.example.mvcasync.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AsyncMvcConfig implements WebMvcConfigurer {

    @Bean("mvcAsyncExecutor")
    public ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("mvc-worker-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        return executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        // @Configuration sử dụng Spring-managed @Bean method.
        configurer.setTaskExecutor(mvcAsyncExecutor());
        configurer.setDefaultTimeout(10_000L);
    }
}
~~~

Ở `@Configuration` tiêu chuẩn (mặc định proxy bean methods được bật), gọi `mvcAsyncExecutor()` trong class nhận managed singleton bean; Spring quản lý initialization/shutdown. `ThreadPoolTaskExecutor` được dùng cả cho `Callable` của MVC và được injection vào controller cho nguồn hoàn thành `DeferredResult`. `setDefaultTimeout` quy định timeout async mặc định **10.000 milliseconds**; trong code dưới `DeferredResult`/`WebAsyncTask` có timeout riêng.

**Production:** sizing 4/8/64 chỉ là demo. Chọn pool/queue theo tải thực, workload blocking hay CPU-bound, thread memory, queue-wait timeout, overload behavior, metrics và shutdown. Timeout đợi queue cũng được tính vào thời gian chờ của request trong thực tế; không đo mỗi thời gian `call()`.

### 10.4. Hai exception public

`src/main/java/com/example/mvcasync/web/MissingItemException.java`:

~~~java
package com.example.mvcasync.web;

public class MissingItemException extends RuntimeException {

    public MissingItemException(long id) {
        super("Item " + id + " does not exist");
    }
}
~~~

`src/main/java/com/example/mvcasync/web/WorkTimedOutException.java`:

~~~java
package com.example.mvcasync.web;

public class WorkTimedOutException extends RuntimeException {

    public WorkTimedOutException() {
        super("Async operation timed out");
    }
}
~~~

Ở ứng dụng thật, exception messages nội bộ không nên phản chiếu trực tiếp nếu chứa identifiers hoặc dữ liệu nhạy cảm. Advice sẽ trả safe detail thay vì `ex.getMessage()`.

### 10.5. Controller đủ ba kiểu kết quả

`src/main/java/com/example/mvcasync/web/AsyncController.java`:

~~~java
package com.example.mvcasync.web;

import java.util.concurrent.Callable;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.context.request.async.WebAsyncTask;

@RestController
@RequestMapping("/api/async")
public class AsyncController {

    public record Payload(long id, String state) {}

    private final AsyncTaskExecutor executor;

    public AsyncController(AsyncTaskExecutor mvcAsyncExecutor) {
        this.executor = mvcAsyncExecutor;
    }

    private ResponseEntity<Payload> find(long id) {
        if (id <= 0) {
            throw new MissingItemException(id);
        }
        return ResponseEntity.ok(new Payload(id, "ready"));
    }

    @GetMapping("/callable/{id}")
    public Callable<ResponseEntity<Payload>> callable(
            @PathVariable("id") long id) {
        return () -> find(id);
    }

    @GetMapping("/deferred/{id}")
    public DeferredResult<ResponseEntity<Payload>> deferred(
            @PathVariable("id") long id) {

        DeferredResult<ResponseEntity<Payload>> result =
                new DeferredResult<>(5_000L);

        result.onTimeout(() ->
                result.setErrorResult(new WorkTimedOutException()));

        result.onCompletion(() -> {
            // Không giữ kết quả trong queue/registry sau completion.
        });

        try {
            executor.execute(() -> {
                try {
                    result.setResult(find(id));
                } catch (Exception ex) {
                    result.setErrorResult(ex);
                }
            });
        } catch (RuntimeException rejected) {
            result.setErrorResult(rejected);
        }

        return result;
    }

    @GetMapping("/web-task/{id}")
    public WebAsyncTask<ResponseEntity<Payload>> webTask(
            @PathVariable("id") long id) {

        WebAsyncTask<ResponseEntity<Payload>> task =
                new WebAsyncTask<>(3_000L, () -> find(id));

        task.onTimeout(() -> {
            throw new WorkTimedOutException();
        });

        return task;
    }
}
~~~

**Giải thích và những điểm cần nhớ:**
- `find(id)` chỉ dựng fixture hoặc ném exception khi `id <= 0`; không thực hiện DB/network. Tất cả các ví dụ cuối cùng trả `Payload` giống nhau.
- `callable`: method controller **chạy trên REQUEST thread**, nhưng lambda `() -> find(id)` chạy trên executor do MVC submit. Exception trong lambda được Spring thu và đưa qua ASYNC dispatch.
- `deferred`: MVC **không tự submit công việc** của `DeferredResult`; controller gửi task qua injected executor. Khi thành công gọi `setResult`; khi lỗi trong task, **phải gọi `setErrorResult`**, nếu không MVC không biết exception của thread tùy biến.
- `deferred` timeout sau 5 giây theo cấu hình holder, callback đẩy `WorkTimedOutException` nếu chưa có result.
- `webTask` có timeout 3 giây, callback trả/đẩy alternate error. Exception ném từ callback timeout được Spring's async interception xử lý theo contract; trong deployment thực cần kiểm mapping/error branch riêng, không giả định callback có thể làm I/O dài.
- Catch quanh `executor.execute` chỉ nhằm minh họa việc task submission có thể bị từ chối; ở hệ thống thực, map task rejection thành error chính sách 503 với an toàn thông tin, không trả raw exception.

**Một tinh chỉnh trước khi dùng production:** `onTimeout` của `WebAsyncTask` có thể dùng `return` một alternate `ResponseEntity` phù hợp thay vì ném exception; điều này giảm sự phụ thuộc vào exception path trong callback. Nếu cần trả lỗi theo ProblemDetail như các nhánh khác, có thể đăng ký callback trả exception object khi dùng loại kết quả thích hợp hoặc viết resolver có kiểm thử đầy đủ. Bài demo chỉ test success/error từ `Callable`/`DeferredResult`, không mô phỏng timer thật.

### 10.6. Advice chuyển exception thành error response chuẩn

`src/main/java/com/example/mvcasync/web/AsyncErrorAdvice.java`:

~~~java
package com.example.mvcasync.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class AsyncErrorAdvice {

    @ExceptionHandler(MissingItemException.class)
    public ResponseEntity<ProblemDetail> missing(
            MissingItemException ex) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Item not found");
        problem.setDetail("The requested item does not exist.");
        problem.setProperty("code", "ITEM_NOT_FOUND");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    @ExceptionHandler(WorkTimedOutException.class)
    public ResponseEntity<ProblemDetail> timeout(
            WorkTimedOutException ex) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.SERVICE_UNAVAILABLE);
        problem.setTitle("Operation timed out");
        problem.setDetail("The operation could not finish in time.");
        problem.setProperty("code", "ASYNC_TIMEOUT");
        return ResponseEntity.status(
                HttpStatus.SERVICE_UNAVAILABLE).body(problem);
    }
}
~~~

`ProblemDetail` là Spring 6 HTTP API dựa trên RFC 9457. Với Jackson support trong Spring MVC, `setProperty("code", ...)` thường trở thành extension field `code` ở top-level JSON.

HTTP 404/503 chỉ là demo's contract: không nên dùng 503 cho **mọi** failure. Network gateway timeout 504, upstream failure 502 hoặc overload 503 có semantics khác nhau; xác định dựa trên loại lỗi và nơi nó xảy ra. Không trả exception raw message ra JSON.

## 11. MockMvc: cần hai pha test, không chỉ `asyncStarted`

`MockMvc` không tự động xử lý container async dispatch cho bạn như một server đang chạy. Với handler bất đồng bộ, thứ tự kiểm thử chính xác là:
1. `mvc.perform(get(...))` lần đầu.
2. Assert `request().asyncStarted()` và lấy `MvcResult`.
3. `mvc.perform(asyncDispatch(first))` để hoàn tất xử lý kết quả trong test.
4. Assert **HTTP status/body cuối**.

### 11.1. Bộ kiểm thử runnable

`src/test/java/com/example/mvcasync/web/AsyncControllerTest.java`:

~~~java
package com.example.mvcasync.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void callableSuccessNeedsAsyncDispatch() throws Exception {
        MvcResult started = mvc.perform(
                        get("/api/async/callable/7"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.state").value("ready"));
    }

    @Test
    void callableExceptionIsHandledOnResume() throws Exception {
        MvcResult started = mvc.perform(
                        get("/api/async/callable/0"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(started))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("ITEM_NOT_FOUND"))
                .andExpect(jsonPath("$.status").value(404));
    }

    @Test
    void deferredSuccessIsSerializedAfterResume() throws Exception {
        MvcResult started = mvc.perform(
                        get("/api/async/deferred/9"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(9))
                .andExpect(jsonPath("$.state").value("ready"));
    }

    @Test
    void deferredSetErrorResultGoesThroughAdvice() throws Exception {
        MvcResult started = mvc.perform(
                        get("/api/async/deferred/0"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(started))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("ITEM_NOT_FOUND"))
                .andExpect(jsonPath("$.status").value(404));
    }

    @Test
    void webAsyncTaskSuccessNeedsDispatch() throws Exception {
        MvcResult started = mvc.perform(
                        get("/api/async/web-task/11"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(11));
    }
}
~~~

Chạy trong thư mục project có Gradle wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell/CMD:

~~~powershell
.\gradlew.bat test
~~~

**Đọc đúng mục đích test:** Spring MVC MockMvc support đợi async result khi dispatch, nhưng test không chứng minh network disconnect, Servlet container timeout, filter ASYNC registrations hoặc thread pool behavior dưới tải thật. Không assert tên thread cố định, không cần `Thread.sleep` để chứng minh dispatch. Cấu hình executor hiện tại bảo đảm thực thi non-blocking ở servlet REQUEST thread khi MVC trao việc cho worker; việc worker hoàn thành rất nhanh không thay nguyên tắc lifecycle.

### 11.2. Test sai điển hình

~~~java
mvc.perform(get("/api/async/callable/7"))
        .andExpect(status().isOk());
~~~

Đoạn test có thể chỉ nhìn **status ban đầu** trước khi JSON serialization hoàn tất, không xác minh body cuối hay error handling. Kể cả `status().isOk()` pass trước dispatch, nó **không chứng minh task thành công**. Luôn assert `request().asyncStarted()` và làm `asyncDispatch(...)` cho các dạng return value bất đồng bộ.

### 11.3. Khi dùng WebTestClient thay MockMvc

Spring MVC có cách dùng WebTestClient gắn với MockMvc; những abstraction test cao hơn có thể tự động xử lý async, nên không copy cơ học hai pha MockMvc sang mọi client. Nếu dùng HTTP client thực tới embedded Tomcat, client thường chỉ thấy response cuối, không có “API call asyncDispatch” phía client.

## 12. Quan sát HTTP trên server thực

Chạy:

~~~bash
./gradlew bootRun
~~~

Thành công:

~~~bash
curl -i 'http://localhost:8080/api/async/callable/7'
curl -i 'http://localhost:8080/api/async/deferred/9'
curl -i 'http://localhost:8080/api/async/web-task/11'
~~~

Dự kiến mỗi response có HTTP **200** và JSON như:

~~~json
{"id":7,"state":"ready"}
~~~

Ở deferred/9 thì `id=9`, web-task/11 thì `id=11`.

Thử exception:

~~~bash
curl -i 'http://localhost:8080/api/async/callable/0'
curl -i 'http://localhost:8080/api/async/deferred/0'
~~~

Dự kiến HTTP **404** với `ProblemDetail` và extension:

~~~json
{
  "type":"about:blank",
  "title":"Item not found",
  "status":404,
  "detail":"The requested item does not exist.",
  "code":"ITEM_NOT_FOUND"
}
~~~

`instance` có thể được thêm tự động theo request path tùy Spring/Jackson handling. Snippet JSON trên chỉ nêu fields chủ yếu. **curl chỉ thấy một HTTP response cuối**; không thể suy ra số Servlet dispatch chỉ từ `curl -i`. Dùng application tracing/debug logs hoặc một interceptor đã được instrument nếu bạn cần quan sát pha nội bộ.

## 13. Lỗi xảy ra ở đâu thì xử lý ở đó

| Nơi lỗi xảy ra | Ví dụ | MVC có nhận được tự động? | Cách xử lý |
| --- | --- | --- | --- |
| Controller trước khi trả async handle | Validate parameter thất bại | Có, như synchronous MVC | `@ExceptionHandler`, validation/error response |
| Bên trong `Callable.call()` | Remote service exception | Có, Spring thu exception thành async result | Advice/error resolver ở ASYNC dispatch |
| Bên trong `WebAsyncTask` Callable | Worker throw | Có, giống Callable | Advice/error resolver |
| Runnable riêng của `DeferredResult` | Throw không catch | **Không**, MVC chỉ biết holder chưa hoàn thành | Catch và `setErrorResult(exception)` |
| Callback `setErrorResult(exception)` | Event báo không tồn tại | Có, khi được chấp nhận | ASYNC dispatch rồi advice |
| DeferredResult timeout callback | Holder chưa có result | Theo callback/result/interceptor | Set error/alternate result, log và cleanup |
| Servlet async timeout mặc định | Request đợi quá lâu | Thường thành `AsyncRequestTimeoutException` | 503 mặc định hoặc policy riêng |
| Response streaming đã commit | Network disconnect/write IOException | Không đảm bảo đổi body/status được | Cleanup/log an toàn, emitter/completion API |
| Executor reject khi submit | Pool/queue quá tải | Tùy điểm throw/cấu hình | Bounded overload policy, 503/metrics/test |
| Worker background không gắn request | Scheduled job ném exception | Không | Job error handling/retry/dead-letter độc lập |

Dùng `@RestControllerAdvice` không có nghĩa bắt được exception trong mọi thread ở JVM. Điều kiện là lỗi có đi qua **cơ chế result/exception handling của MVC**. Spring MVC async giúp bạn làm điều đó với Callable/WebAsyncTask/DeferredResult khi dùng đúng cách.

## 14. Observability: đừng nhân đôi request count vì dispatch thứ hai

Vì cùng HTTP request có thể đi qua filters/interceptors hai lần ở hai dispatcher types, analytics không nên đếm mỗi `preHandle` hoặc `doFilter` như một business request nếu chúng chạy cho cả REQUEST và ASYNC.

Khuyến nghị:
- Dùng metric HTTP server được framework đo đúng vòng đời response nếu có.
- Khi tự instrument, gắn một request ID/attribute và xác định bắt đầu/kết thúc logical request một lần.
- Log dispatcher type, phase, trace ID và duration, **không log tokens/cookies/body nhạy cảm**.
- Với worker, truyền tracing/MDC context có kiểm soát và clear khi dùng pooled threads.
- Đo executor active count, pool/queue size, task rejection, timeout rate, p95/p99 latency, downstream wait time.
- Tách timeout của proxy/client/service/container; đừng nhìn một metric “async timeout” rồi kết luận DB có vấn đề.

Giả sử worker bắt đầu sau 9 giây chờ queue và Spring MVC timeout là 10 giây. Dù business computation chỉ mất 2 giây, request có thể timeout trước khi worker trả. Monitoring phải phân biệt queue time với execution time.

## 15. MVC async so với Java `@Async`, CompletableFuture và WebFlux

### 15.1. `@Async` của Spring

`@Async` là cơ chế Spring chạy method trên executor thông qua AOP proxy, khi được enable và gọi đúng proxy boundary. Nó **không tự làm HTTP response dùng Servlet ASYNC dispatch** chỉ vì service được annotate. Nếu controller chờ `future.get()`, servlet request thread vẫn block.

Để làm MVC async, controller phải trả một loại return value mà MVC nhận diện như `Callable`, `DeferredResult`, `CompletionStage/CompletableFuture` phù hợp, hoặc reactive single-result adapter. Kiểm phiên bản/adapter khi sử dụng và xử lý cancellation/exception rõ.

### 15.2. `CompletableFuture` và context propagation

`CompletableFuture.supplyAsync(...)` nếu không chỉ executor có thể sử dụng common ForkJoinPool. Điều đó dễ gây khó dự đoán về throughput, trace context, transaction/security context và workload isolation. Với request-scoped workloads, ưu tiên dedicated bounded executor hoặc async HTTP client phù hợp. MVC biết xử lý một số async return types qua adapters, nhưng việc một future được chạy **ở đâu** vẫn là trách nhiệm ứng dụng.

### 15.3. Spring MVC async không phải WebFlux

| Đặc điểm | Spring MVC async | Spring WebFlux |
| --- | --- | --- |
| Nền HTTP server | Servlet API | Reactive/non-blocking stack |
| Lượt dispatch `ASYNC` Servlet | Có khi dùng async support | Không cùng cơ chế Servlet MVC |
| Controller return `Callable`/`DeferredResult` | Hỗ trợ | Không phải programming model chủ đạo |
| Blocking JDBC trong worker | Vẫn chiếm worker thread | Cũng phải offload nếu gọi blocking code |
| HTTP response stream writes | Có thể blocking qua executor | Dựa trên non-blocking reactive I/O |
| Bối cảnh sử dụng | Mở rộng MVC hiện hữu | End-to-end reactive/streaming khi phù hợp |

Không chuyển sang WebFlux chỉ vì thấy chữ “async”; cần đánh giá library chain, team familiarity, thread model, tracing, backpressure và kiểm thử. Nếu chỉ đợi một số external calls trong ứng dụng MVC, Servlet async thường đủ.

## 16. Những lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách giải quyết |
| --- | --- | --- |
| Controller trả Callable nhưng thread vẫn đông | Callable thực hiện I/O blocking trong worker | Đo pool/queue; cân nhắc async I/O hoặc tăng năng lực phù hợp |
| `IllegalStateException` khi start async | Servlet/filter không có `asyncSupported` | Cấu hình Servlet/Filter và dispatcher types |
| Client chờ mãi với DeferredResult | Không gọi setResult/setErrorResult | Đảm bảo mọi nhánh thành công/lỗi/timeout hoàn tất |
| Worker logs lỗi nhưng client nhận 503 timeout | Runnable throw không gọi setErrorResult | Catch và đưa exception vào DeferredResult |
| `@ExceptionHandler` không chạy | Lỗi xảy ra ngoài MVC async flow hoặc response đã commit | Đưa qua holder, dùng appropriate error flow |
| MockMvc assert 200 nhưng JSON rỗng | Chỉ kiểm initial perform | Gọi `asyncDispatch(MvcResult)` |
| Interceptor double-count metric | preHandle chạy lại ở ASYNC | Phân biệt phase/dispatcher type |
| MDC mất hoặc user hiện sai | ThreadLocal không tự propagate hoặc bị leak | Context propagation và cleanup có kiểm soát |
| `SecurityContextHolder` rỗng trong worker custom | Callback không qua tích hợp Callable Security | Truyền trusted principal/context qua executor wrapper |
| `@Transactional` không còn trên worker | Transaction context thread-bound | Mở transaction ở service đúng thread |
| Timeout luôn sau 30s dù MVC đặt 120s | Proxy/client/LB timeout ngắn hơn | Cấu hình tổng thể và kiểm network |
| Async timeout sau khi công việc hoàn tất | Race/queue backlog/task result đến muộn | Kiểm setResult boolean, metrics và cancellation |
| Hàng nghìn worker threads khi tải lớn | Executor không giới hạn | Dùng bounded pool/queue và overload handling |
| JSON 500 bị lộ raw exception | Catch-all advice trả ex.getMessage() | Safe ProblemDetail + internal logs |
| Background task hoàn thành sau client disconnect | Không có cancel/cleanup | Kiểm idempotency, timeout và lifecycle callbacks |
| `ResponseBodyEmitter` đã commit rồi vẫn muốn đổi 404 | HTTP status/headers đã gửi | Xử lý streaming protocol/error riêng |
| Gọi controller method hai lần do nghĩ ASYNC là request mới | Hiểu nhầm mapping trong redispatch | MVC dùng stored result, không gọi lại method |
| `Thread.sleep` trong timeout callback | Blocking container thread | Callback nhanh; schedule cleanup ngoài nếu cần |

## 17. Checklist production

1. Xác nhận container, DispatcherServlet và filter mapping hỗ trợ Servlet async.
2. Chọn đúng kiểu: Callable cho computation MVC-managed; DeferredResult cho external event/completion; WebAsyncTask cho cấu hình Callable per-request.
3. Đặt MVC async timeout và per-dependency timeout; xác nhận LB/client timeout không ngắn hơn ngoài ý muốn.
4. Dùng executor có giới hạn với metrics/rejection policy rõ ràng; không tạo unbounded threads.
5. Đảm bảo mọi callback DeferredResult có nhánh `setResult` hoặc `setErrorResult`.
6. Dùng `@ExceptionHandler`/`ProblemDetail` cho known errors, giữ status/body an toàn.
7. Xét timeout/result race, cancellation, cleanup và pending-registration leaks.
8. Không dựa vào ThreadLocal/MDC/SecurityContext/transaction context tự lan qua threads.
9. Phân biệt `REQUEST` và `ASYNC` để không đếm/dùng business side effects hai lần.
10. Kiểm AsyncHandlerInterceptor và OncePerRequestFilter nếu cần áp dụng logic ở redispatch.
11. Test MockMvc theo hai pha và thêm integration HTTP/container tests cho timeout/disconnect/security.
12. Nếu streaming, kiểm hành vi khi response đã commit; không giả định có thể thay status.
13. Tách các job thực sự dài sang queue/job status endpoint thay vì giữ HTTP connection vô hạn.
14. Kiểm sensitive data trong log, trace, exception và security context propagation.
15. Đo thread pool, queue, response latency và errors sau mỗi thay đổi executor/config.

### Câu hỏi tự kiểm tra

**1.** Trong Callable, method controller có được gọi lại ở lần ASYNC dispatch không?

**Trả lời:** Không. Spring MVC map handler để tiếp tục, nhưng dùng **concurrent result đã lưu**, không chạy lại business code trong controller method.

**2.** HTTP client gửi mấy request nếu server xử lý REQUEST và ASYNC?

**Trả lời:** Một HTTP request. REQUEST/ASYNC là hai Servlet dispatch nội bộ, client thấy một response hoàn tất.

**3.** `Callable` ném exception trên worker có vào `@RestControllerAdvice` được không?

**Trả lời:** Có, khi Spring MVC đang quản lý Callable, exception được giữ làm result và xử lý ở lượt ASYNC dispatch.

**4.** Tại sao exception trong executor runnable của DeferredResult không tự tới advice?

**Trả lời:** Runnable độc lập không được Spring tự liên kết với DeferredResult; ứng dụng phải catch và gọi `setErrorResult(exception)`.

**5.** `DeferredResult.setResult(...)` trả true có nghĩa client đã nhận response chưa?

**Trả lời:** Chưa. Chỉ phản ánh holder chấp nhận thiết lập result; sau đó còn async dispatch, conversion và network write.

**6.** Vì sao MockMvc cần `asyncDispatch`?

**Trả lời:** MockMvc mô phỏng Servlet processing nhưng không tự hoàn tất async request như embedded container; phải dispatch tiếp để test status/body cuối.

**7.** `WebAsyncTask.onTimeout` có nên gọi HTTP client 10 giây để retry không?

**Trả lời:** Không. Timeout callback chạy trong container thread và phải nhanh; xử lý retry/background việc nặng bên ngoài, có bounded resources.

**8.** Spring MVC async có giải phóng mọi thread trong khi JDBC đang chạy không?

**Trả lời:** Không. Servlet request thread được trả lại pool, nhưng JDBC blocking vẫn chiếm executor worker.

**9.** Sau khi `ResponseBodyEmitter` đã gửi một phần body, có thể đổi status thành 404 không?

**Trả lời:** Thường không vì response có thể đã commit; phải xử lý lỗi streaming theo protocol tương ứng.

## 18. Tài liệu chính thức

- [Spring Framework 6.2 — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): Callable, DeferredResult, WebAsyncTask, processing, error handling, interceptor, streaming và Servlet configuration.
- [Spring Framework 6.1 — WebAsyncManager Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/context/request/async/WebAsyncManager.html): start, concurrent result, dispatch lifecycle.
- [Spring Framework 6.1 — DeferredResult Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/context/request/async/DeferredResult.html): `setResult`, `setErrorResult`, timeout/error/completion callbacks.
- [Spring Framework 6.1 — WebAsyncTask Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/context/request/async/WebAsyncTask.html): per-task timeout, executor, timeout/error/completion.
- [Spring Framework 6.1 — AsyncHandlerInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/servlet/AsyncHandlerInterceptor.html): `afterConcurrentHandlingStarted` và lifecycle interceptor.
- [Spring Framework — MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): `request().asyncStarted()`, `request().asyncResult(...)` và `asyncDispatch`.
- [Spring Framework — MVC Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/async-support.html): `configureAsyncSupport`, task executor và timeout.
- [Jakarta Servlet 6.0 — AsyncContext](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/asynccontext): `dispatch`/`complete`, timeout/listeners.
- [Spring Security — Servlet Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html): integration points và security context.
- [Spring Framework — Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): error response API và exception handling.

**Ghi nhớ:** Spring MVC async không trả response ngay và cũng không tạo “request thứ hai” ở browser. Controller trả **Callable/DeferredResult/WebAsyncTask**, Servlet giải phóng request thread rồi **ASYNC dispatch** khi có kết quả/lỗi. Thành công đi qua return-value processing; lỗi đúng nguồn đi qua exception resolvers; timeout/cleanup/context propagation cần được cấu hình và kiểm thử. Trong MockMvc, đừng dừng ở `asyncStarted`: phải gọi `asyncDispatch` và kiểm tra HTTP response cuối.
