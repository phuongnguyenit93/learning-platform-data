# Callable, DeferredResult, WebAsyncTask và lựa chọn mô hình hoàn thành trong Spring MVC

## 1. Mục tiêu: trả HTTP response sau khi công việc hoàn tất

Ở Spring MVC đồng bộ, một Servlet container thread nhận request, chạy controller, chờ truy vấn DB/dịch vụ ngoài, tạo kết quả, rồi ghi response. Nếu việc tính kết quả phải chờ lâu, thread xử lý request có thể bị giữ trong lúc chờ.

Spring MVC có hỗ trợ **asynchronous Servlet request processing**. Controller có thể trả một **giá trị đại diện cho kết quả sẽ xuất hiện trong tương lai**. Spring bắt đầu async mode, giải phóng Servlet request thread ban đầu và để response mở. Khi kết quả sẵn sàng, MVC thực hiện **ASYNC dispatch** để tiếp tục xử lý kết quả, áp dụng handler return-value processing (JSON/view/error) và hoàn tất response.

Ba lựa chọn rất hay gặp:

- `Callable<T>` — controller giao **một tác vụ tính kết quả** để Spring MVC thực thi bằng `AsyncTaskExecutor`.
- `DeferredResult<T>` — controller giao **một điểm nhận kết quả**; ứng dụng hoặc event/callback ở bên ngoài sẽ tự gọi `setResult(...)` hoặc `setErrorResult(...)`.
- `WebAsyncTask<T>` — bọc `Callable<T>` và cho phép cấu hình **timeout, executor, onTimeout/onError/onCompletion** cho riêng request.

Đây là bài học về **cách chọn mô hình hoàn thành**, không chỉ ba kiểu Java được phép return. Cần hiểu ai sở hữu tác vụ, ai kết thúc response, timeout tính thế nào, quản lý tài nguyên chờ ra sao, và khi nào nên chọn reactive/streaming thay vì các kiểu một-kết-quả này.

### Kết quả học tập

Sau bài, bạn có thể:

1. Vẽ đúng luồng `REQUEST → startAsync → giải phóng container thread → ASYNC redispatch → response`.
2. Phân biệt `Callable`, `DeferredResult` và `WebAsyncTask` theo **producer, thread, completion trigger, timeout và cleanup**.
3. Cấu hình executor MVC bằng `WebMvcConfigurer#configureAsyncSupport`; hiểu lý do executor mặc định không nên mặc nhiên dùng dưới tải cao.
4. Xử lý `setErrorResult`, exceptions, `@ExceptionHandler`, timeout, lỗi network/client disconnect và bất đồng bộ kết thúc đua nhau.
5. Thiết kế endpoint không leak DeferredResult trong map, không giữ request thread bằng `Future#get()`, không dựa mù quáng vào thread-local.
6. Chạy ví dụ Spring Boot 3 + Java 17 và kiểm tra `request().asyncStarted()` cùng `asyncDispatch(...)` bằng MockMvc.

**Phạm vi:** Spring Framework 6.x/Spring Boot 3.x, Jakarta Servlet API và Spring MVC (Servlet stack). Spring WebFlux có mô hình reactive riêng. Trả `Callable`/`DeferredResult` không tự biến toàn bộ Spring MVC, JDBC hay HttpServletResponse thành non-blocking I/O.

## 2. Servlet async: giải phóng request thread nhưng chưa trả xong response

Synchronous request:

```text
Servlet thread T1
┌────────────────────────────────────────────────────┐
│ GET /report                                        │
│   → filters → DispatcherServlet → controller       │
│   → đọc DB/chờ remote service → tạo body           │
│   → Jackson/View render → HTTP 200 → thread rảnh   │
└────────────────────────────────────────────────────┘
         giữ Servlet thread trong toàn bộ thời gian chờ
```

Spring MVC async:

```text
T1: Servlet container thread                  T2: worker/event thread
──────────────────────────                    ─────────────────────────
GET /report
  → filters → DispatcherServlet
  → controller trả Callable hoặc DeferredResult
  → ServletRequest.startAsync()
  → T1 rời filter/Servlet chain
      response VẪN mở                       Callable chạy / event chờ...
                                            └── tạo kết quả
                                                hoặc setResult(...)
                           │
                           ▼
T3: Servlet container ASYNC redispatch
  → DispatcherServlet tiếp tục với kết quả đã có
  → ResponseEntity/JSON/View/error handler
  → HTTP 200/4xx/5xx
  → hoàn tất async request
```

Những sự thật quan trọng:

- Khi thread ban đầu rời request processing, **HTTP response chưa nhất thiết được gửi xong**. Browser vẫn đợi.
- Trong `ASYNC` redispatch, MVC có thể map cùng URL nhưng **không gọi lại controller method ban đầu như một request mới**; nó tiếp tục xử lý giá trị async đã lưu.
- `ASYNC` dispatch khác `forward:`, khác `redirect:` và khác việc người dùng mở một HTTP connection mới.
- Chuyển sang async **không có nghĩa công việc CPU/DB biến mất**. `Callable` chỉ chuyển blocking work khỏi container thread sang executor thread.
- DeferredResult có thể hiệu quả với producer thật sự callback/event-based: thread Servlet rảnh **và** không cần thêm thread ngồi đợi kết quả. Nhưng nếu tự `new Thread(...).sleep(...)` cho mỗi DeferredResult, bạn chỉ chuyển vấn đề sang chỗ khác.
- Response cuối cùng vẫn đi qua xử lý của Spring MVC, nên exceptions và message conversion còn hoạt động theo quy tắc của Framework.

### 2.1. Servlet prerequisites

Servlet async phải được enable cho `DispatcherServlet` và các Servlet filters có liên quan, với `asyncSupported=true`; filter nào cần tham gia ASYNC redispatch phải được map cho `DispatcherType.ASYNC`. Trong Spring Boot Servlet MVC cấu hình thông thường, Boot quản lý nhiều phần này. Với `web.xml`, filter registration tùy chỉnh hoặc triển khai WAR riêng, phải xác nhận bằng kiểm thử container thực tế.

Ví dụ mapping cho custom filter:

```java
registration.setAsyncSupported(true);
registration.setDispatcherTypes(
    DispatcherType.REQUEST, DispatcherType.ASYNC);
```

*Đây là đoạn minh họa của FilterRegistrationBean/Servlet registration, không phải file Java độc lập.*

`OncePerRequestFilter` có chính sách tham gia redispatch riêng qua `shouldNotFilterAsyncDispatch()`. Một Filter chỉ có flag `asyncSupported` chưa chắc được gọi ở ASYNC dispatch; mapping, filter behavior và container đều quan trọng.

## 3. Bảng quyết định nhanh: ai hoàn thành kết quả?

| Tiêu chí | `Callable<T>` | `DeferredResult<T>` | `WebAsyncTask<T>` |
| --- | --- | --- | --- |
| Ai thực thi? | Spring MVC submit callable vào AsyncTaskExecutor | Producer do ứng dụng quản lý: message/event/webhook/callback | Như Callable nhưng executor có thể tùy chỉnh |
| Kích hoạt completion | Callable return/throw | Ứng dụng gọi `setResult` / `setErrorResult` | Callable return/throw hoặc timeout/error callback |
| Có cần giữ pending handle? | Không, MVC quản lý Callable | Thường có, nếu callback ở bên ngoài cần tìm đúng handle | Không, MVC quản lý callable |
| Timeout riêng request | Không trực tiếp trên Java Callable | `new DeferredResult<>(timeoutMillis)` | `new WebAsyncTask<>(timeoutMillis, callable)` |
| Hook timeout | Qua MVC global CallableProcessingInterceptor | `onTimeout(Runnable)` | `onTimeout(Callable<T>)` |
| Hook error | Qua MVC global interceptor / MVC exception handling | `onError(Consumer<Throwable>)`, `setErrorResult` | `onError(Callable<T>)` |
| Hook completion | Qua MVC global interceptor | `onCompletion(Runnable)` | `onCompletion(Runnable)` |
| Executor riêng request | Cấu hình MVC global hoặc tự quản task bên ngoài | Không bắt buộc có executor để tự hoàn thành | Có thể chỉ định một AsyncTaskExecutor hoặc bean name |
| Điển hình | Blocking service cần chạy ngoài Servlet thread | Chờ kết quả bất ngờ/đến từ event bus | Blocking task có SLA/executor khác mặc định |
| Rủi ro chính | Executor pool/queue đầy, blocking vẫn còn | Pending map leak, timeout/callback race | Như Callable + hiểu sai callback/cancellation |

**Câu hỏi chọn mô hình tốt nhất:** “Kết quả sẽ xuất hiện **bằng cách nào**?” Nếu bạn đã có một callable phải thực thi, chọn Callable/WebAsyncTask. Nếu một sự kiện độc lập sẽ quyết định khi nào có kết quả, chọn DeferredResult.

## 4. Callable<T>: giao tác vụ để Spring thực thi

Controller có thể trả:

```java
@GetMapping("/api/report")
public Callable<ResponseEntity<String>> report() {
    return () -> {
        String result = slowBlockingService.buildReport();
        return ResponseEntity.ok(result);
    };
}
```

*Đây là đoạn minh họa trong @RestController có slowBlockingService được inject; ví dụ chạy độc lập ở mục 10.*

Luồng:

```text
Controller thread T1:
  tạo Callable → return → Spring startAsync → T1 rảnh

MVC AsyncTaskExecutor thread T2:
  call() chạy
    ├── success → result được lưu
    └── exception → exception được lưu

Container thread T3:
  ASYNC dispatch → Spring xử lý ResponseEntity, View hoặc exception
```

### 4.1. Callable không đồng nghĩa non-blocking service

Nếu `slowBlockingService.buildReport()` vẫn dùng JDBC blocking, thread T2 vẫn bị giữ trong lúc DB xử lý. Lợi ích là **không giữ một Servlet container thread** cho tác vụ, giúp thread container sẵn sàng tiếp nhận request mới. Nhưng tổng thread và tài nguyên DB vẫn phải đủ; nếu queue executor tăng vô hạn, latency và memory có thể tệ hơn synchronous request.

Không làm thế này trong controller:

```java
@GetMapping("/wrong")
public String wrong() throws Exception {
    Future<String> future = executor.submit(this::slowCall);
    return future.get(); // Servlet thread T1 vẫn chờ!
}
```

Code trên là minh họa **anti-pattern**, không compile độc lập nếu thiếu field/helper. Việc gọi `get()` trực tiếp **đánh mất** mục đích Servlet async. Hãy return Callable hoặc biểu diễn kết quả tương lai được MVC hỗ trợ.

### 4.2. Chọn Callable khi nào?

- Tác vụ có một điểm bắt đầu và kết thúc rõ, không phải chờ message/event bên ngoài.
- Muốn MVC tự submit và quản lý giá trị trả về/exception.
- Không cần timeout hoặc executor riêng từng endpoint, có thể dùng cấu hình global.
- Service đã blocking nhưng bạn có đủ thread/connection pool và muốn trả Servlet thread sớm.

Không chọn chỉ vì “controller phải nhanh”: đo throughput, queue, DB connections và tail latency trước/sau.

## 5. WebAsyncTask<T>: Callable với SLA và executor riêng

`WebAsyncTask<T>` chứa một `Callable<T>` giống mô hình trên, đồng thời mang cấu hình timeout và executor tùy chọn, cùng callback quản lý lifecycle.

```java
@GetMapping("/api/report-with-deadline")
public WebAsyncTask<ResponseEntity<String>> report() {
    WebAsyncTask<ResponseEntity<String>> task =
        new WebAsyncTask<>(5_000L,
            () -> ResponseEntity.ok("report-ready"));

    task.onTimeout(() ->
        ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                      .body("report-timeout"));

    task.onError(() ->
        ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                      .body("report-error"));

    task.onCompletion(() ->
        logger.debug("HTTP async processing finished"));

    return task;
}
```

*Đoạn minh họa của controller có logger; project runnable dùng tên endpoint khác và import đầy đủ.*

### 5.1. Các callback có cùng kiểu không?

Không:

- `onTimeout(Callable<T>)` nhận một callback **trả giá trị T** (hoặc exception) làm kết quả thay thế khi Servlet async timeout.
- `onError(Callable<T>)` nhận callback có thể tạo kết quả thay thế khi có async container error.
- `onCompletion(Runnable)` dùng cho **dọn tài nguyên/quan sát** khi async request hoàn thành, bao gồm timeout/error.

Callback timeout/error chạy từ container thread, nên **phải trả nhanh, không chặn**. Không gọi HTTP remote service rất chậm hoặc đợi `Future#get()` trong callback chỉ để tạo fallback.

### 5.2. Timeout không đồng nghĩa hủy business task

Khi client chờ quá timeout:

- Spring/container có thể tạo kết quả timeout/error rồi hoàn tất response.
- Callable đã được submit có thể **vẫn đang chạy**; timeout response **không tự đảm bảo** JDBC/HTTP downstream bị hủy ngay.
- Cần deadlines trong chính client DB/HTTP, cancellation design, interruption handling, idempotency và tracing phù hợp.
- Không nhầm “đã trả 503/504 cho browser” với “mọi công việc backend đều đã dừng”.

Timeout trong `WebAsyncTask<>(5_000L, callable)` tính theo request async lifecycle của Servlet/container, không phải một CPU quota riêng của callable.

### 5.3. Executor theo request

Có thể chọn một executor khác qua các constructors của `WebAsyncTask`, như overload nhận `AsyncTaskExecutor` hoặc bean name executor. Khi endpoint báo cáo cần pool chuyên biệt còn tác vụ ngắn dùng pool mặc định, việc tách có thể giúp bulkhead nhưng phải cấp giới hạn rõ. Không tự tạo `new ThreadPoolTaskExecutor()` **bên trong từng request**.

Nếu cả ứng dụng có một policy tương đối đồng đều, cấu hình `WebMvcConfigurer#configureAsyncSupport` là đơn giản hơn; chỉ dùng executor riêng khi thực sự có workload/priority khác.

## 6. DeferredResult<T>: chờ một producer tự đến, không cần giao Callable

`DeferredResult<T>` là **điểm kết thúc response trong tương lai**. Controller tạo nó, trả ngay, và giữ một reference để nơi khác (event bus, JMS consumer, callback, một request khác) có thể complete.

```java
@GetMapping("/api/jobs/{id}/wait")
public DeferredResult<ResponseEntity<String>> waitForJob(
        @PathVariable String id) {

    DeferredResult<ResponseEntity<String>> result =
        new DeferredResult<>(10_000L);

    pending.put(id, result);

    result.onTimeout(() ->
        result.setResult(ResponseEntity.status(504)
                                       .body("job-timeout")));

    result.onCompletion(() -> pending.remove(id, result));

    return result;
}
```

*Đây là đoạn minh họa trong controller có concurrent pending map; project đầy đủ bên dưới kiểm soát ID trùng và cleanup.*

Một producer khác:

```java
DeferredResult<ResponseEntity<String>> result = pending.get(jobId);
if (result != null) {
    boolean accepted =
        result.setResult(ResponseEntity.ok("job-completed"));
    // false: đã có kết quả, timeout hoặc không còn usable
}
```

Ưu điểm:

- Controller **không cần đợi trong Servlet thread**.
- Producer không nhất thiết là MVC executor: có thể là listener của message broker, callback một client async, event từ domain service.
- Mô hình rất hợp cho **long polling một kết quả**.

Nhưng phải tự quản ownership, correlation ID, timeout, cancellation/disconnect, queue size, cleanup và concurrency.

### 6.1. setResult/setErrorResult là một cuộc đua có thứ tự

`DeferredResult#setResult(value)` trả boolean:

- `true` nếu result mới được set thành công.
- `false` nếu đã có result hoặc request/result đã hết hiệu lực.

Một response chỉ được quyết định một lần: có thể xảy ra cạnh tranh giữa **event đến**, **timeout**, **async error** và **request bị hoàn tất**. Không giả định callback sẽ thắng timeout.

`setErrorResult(exception)` đưa lỗi về MVC exception handling pipeline, có thể được `@ExceptionHandler` hoặc `@ControllerAdvice` xử lý. Nếu truyền một đối tượng response thay vì Throwable qua error-result API, cần hiểu cách Framework diễn giải loại return value; đơn giản hơn khi timeout muốn HTTP 504 thì dùng `setResult(ResponseEntity.status(504).body(...))`.

### 6.2. Cleanup đúng thời điểm

Đối với pending map, điều cần bảo vệ:

- Khi timeout hoặc connection đóng: loại reference khỏi map.
- Khi complete: loại reference khi request thực sự hoàn tất.
- Khi cùng ID có hai waiter: không im lặng ghi đè waiter đầu.
- Khi event tới sau timeout: không dùng object stale; phản ánh `setResult` thất bại.
- Khi producer không gửi gì mãi: timeout/TTL, kiểm soát pending count và backpressure.
- Khi ứng dụng dừng: đóng/wake pending requests bằng policy rõ.

`onCompletion(...)` được gọi khi Servlet async request hoàn thành vì bất kỳ lý do gì, có giá trị để cleanup. `onTimeout(...)` và `onError(...)` là các điểm làm fallback/result, không thay thế toàn bộ cleanup.

### 6.3. Không dùng DeferredResult để giữ thread chờ

Sai:

```java
@GetMapping("/wrong-deferred")
public DeferredResult<String> wrong() {
    DeferredResult<String> dr = new DeferredResult<>();
    executor.execute(() -> {
        try {
            Thread.sleep(10_000); // giữ một thread chỉ để chờ
            dr.setResult("done");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            dr.setErrorResult(e);
        }
    });
    return dr;
}
```

Đây là đoạn minh họa anti-pattern. Nếu công việc đã là một `Callable` blocking, để MVC quản lý thông qua `Callable/WebAsyncTask` thường dễ hơn. Nếu API đã callback-based và không cần thread ngủ chờ, `DeferredResult` mới thể hiện lợi ích đúng.

## 7. Ai sở hữu completion? Ma trận theo kiến trúc

| Nguồn kết quả | Chọn mặc định | Vì sao |
| --- | --- | --- |
| Service blocking tính toán rồi return một giá trị | `Callable<T>` | MVC submit task và quản lý kết quả |
| Service blocking với timeout/SLA riêng | `WebAsyncTask<T>` | Callable + timeout, callbacks, executor riêng |
| JMS/Kafka/message consumer nhận event hoàn thành | `DeferredResult<T>` | Sự kiện tự đến, không cần thread chờ |
| Webhook bên ngoài đánh dấu job xong | `DeferredResult<T>` | Callback complete đang pending |
| Already have `CompletableFuture<T>`/`CompletionStage<T>` | Trả async type được Spring MVC hỗ trợ hoặc adapt phù hợp | Không cần tạo thread chờ/Blocking get |
| Long polling một response sau một event | `DeferredResult<T>` | Một kết quả, timeout và cleanup rõ |
| SSE stream nhiều sự kiện | `SseEmitter` hoặc reactive stream adaptation | Không phù hợp kiểu một giá trị đơn |
| Video/files streaming raw bytes | `StreamingResponseBody` | Cần stream/chunk và quản lý writing thread |
| Luồng non-blocking end-to-end và backpressure | Cân nhắc WebFlux/reactive clients | MVC async không làm JDBC/Servlet writes non-blocking |

**Không quyết định chỉ theo tên class.** Quan trọng là producer thật sự, số lượng responses, khả năng block, data ownership, số concurrent requests, deadlines và expected client behavior.

## 8. Cơ chế timeout, errors và completion

### 8.1. Timeout đến từ đâu?

Các nguồn có thể gồm:

1. Servlet container async timeout (có default khác nhau theo container).
2. MVC global async timeout từ `AsyncSupportConfigurer#setDefaultTimeout(...)`.
3. Per-request timeout ở `DeferredResult<>(milliseconds)` hoặc `WebAsyncTask<>(milliseconds, callable)`.
4. Timeout của DB client, HTTP client, messaging layer.
5. Reverse proxy/API gateway/client timeout — có thể đóng connection **trước** server.
6. Thread pool saturation khiến Callable chưa chạy khi request hết hạn.

Vì vậy “đặt 5 giây cho WebAsyncTask” chưa đủ nếu downstream HTTP client có read timeout 60 giây. Nên có **deadline budget** xuyên các layer: service/read timeout nhỏ hơn request budget và có fallback/cleanup phù hợp.

### 8.2. Giá trị mặc định khi timeout

Nếu bạn không xử lý timeout và response chưa commit, các Spring MVC async timeout interceptors thông thường có thể dẫn tới `AsyncRequestTimeoutException` và HTTP **503 Service Unavailable**. Tuy nhiên response/status cụ thể phụ thuộc framework version, exception handling, container và custom interceptors; không dựa vào điều này thay cho policy explicit.

Trong demo sẽ cho:

- WebAsyncTask timeout → `503` body `webtask-timeout`.
- DeferredResult timeout → `504` body `deferred-timeout`.

Đó là **hợp đồng do ví dụ chủ động lựa chọn**; 503/504 không phải định nghĩa duy nhất của hai loại async.

### 8.3. Exceptions đi qua @ExceptionHandler

Nếu Callable throws, Spring MVC lưu concurrent result dạng exception rồi redispatch. `@ExceptionHandler` hoặc `@RestControllerAdvice` có thể xử lý như lỗi synchronous controller phù hợp.

Với DeferredResult:

```java
result.setErrorResult(
    new IllegalStateException("remote event failed"));
```

Framework có thể đi qua cơ chế exception resolution thông thường. Không trả chuỗi lỗi kỹ thuật nhạy cảm ra client; API error schema nên ổn định và không expose nội dung exception từ hạ tầng.

### 8.4. Completion là kết thúc HTTP, không phải bảo đảm công việc đã hủy

`onCompletion` dùng cho release pending references, dọn context và metrics. Không giả định mọi database operation đều dừng khi HTTP connection ngắt hoặc timeout xảy ra. Nếu side effect nghiệp vụ tiếp tục sau timeout, hãy thiết kế idempotency key, trạng thái job, retry semantics và duplicate suppression.

### 8.5. Callback phải ngắn

Các callbacks timeout/error thường chạy trên Servlet container thread. Thực thi một thao tác chậm trong callback có thể gây nghẽn container pool, trái với mục tiêu async. Callback thường chỉ nên **đặt fallback result, ghi metric nhẹ, đánh dấu hủy, giải phóng reference** rồi thoát.

## 9. Executor, backpressure và context propagation

### 9.1. Cấu hình MVC AsyncTaskExecutor

Spring Framework MVC cho phép:

```java
@Configuration
class MvcAsyncConfig implements WebMvcConfigurer {
    private final AsyncTaskExecutor executor;

    MvcAsyncConfig(
            @Qualifier("mvcExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(10_000L);
    }
}
```

*Đoạn minh họa class configuration; project mục 10 có file và imports đầy đủ.*

Executor mặc định có thể dùng được cho dev nhưng tài liệu Spring cảnh báo **không thích hợp cho production dưới load cao nếu không cấu hình**. Cần đặt các mức core/max pool size, queue capacity và rejection behavior, gắn metric queue length/active threads.

### 9.2. Một executor pool không làm nguồn lực vô hạn

Nếu pool có 4 worker threads và mỗi Callable blocking 10 giây, một lúc chỉ có khoảng 4 tasks chạy blocking trong pool đó. Request khác có thể xếp hàng rồi timeout trước khi có worker.

Vì vậy thiết kế:

- Bound queue và concurrent requests, không để pending map unbounded.
- Đặt timeout/deadline rõ ở app và downstream.
- Chính sách saturation: queue, reject, circuit breaker, retry có backoff.
- DB connection pool và HTTP client pool phải tương ứng.
- Dùng bulkheads để tác vụ chậm không chiếm mọi worker.
- Load test p95/p99, chứ không dựa vào output `asyncStarted=true` để khẳng định throughput tăng.

### 9.3. ThreadLocal, MDC và Spring Security

`LocaleContextHolder`, `RequestContextHolder`, logging MDC, transaction context và một số SecurityContext storage dựa trên thread-local. Khi MVC chuyển từ thread ban đầu sang executor thread, **không giả định mọi context tự di chuyển**.

- Truyền ID/locale/user data cần thiết **một cách tường minh** vào callable/event callback là cách dễ kiểm soát.
- Với logging MDC, sử dụng task decorator/context propagation cho executor.
- Với Spring Security, dùng các integration/context propagation phù hợp (như security context delegation) thay vì tự sao chép mutable SecurityContext sang thread dùng chung mà quên cleanup.
- Transaction của Servlet thread không tự kéo dài sang Callable thread; đặt transaction boundary trong service cần thực thi.
- Với DeferredResult producer chạy ở message listener, request thread context thường **không tồn tại**, nên cần correlation context rõ.

Đừng giữ `HttpServletRequest` hoặc `HttpServletResponse` lâu sau khi HTTP async request hoàn thành; điều đó gây stale references/leaks.

### 9.4. AsyncHandlerInterceptor khác HandlerInterceptor truyền thống

Trong MVC async, callback `preHandle` có thể chạy trong initial dispatch và lại ở redispatch. Khi request bắt đầu concurrent handling, MVC có thể gọi `AsyncHandlerInterceptor#afterConcurrentHandlingStarted` thay vì ngay lập tức gọi `postHandle`/`afterCompletion` cho lượt đầu. Khi ASYNC dispatch xử lý giá trị kết quả, interceptor chain lại tham gia theo quy tắc Framework.

Nếu tính metric “một HTTP request” ở interceptor, không tăng request count mỗi lần preHandle; cần dùng request attribute/correlation ID và completion semantics phù hợp.

## 10. Ví dụ runnable: Spring Boot 3 + Java 17

Ứng dụng có một nhóm endpoint hoàn toàn cụ thể:

- `GET /work/callable` → `Callable<ResponseEntity<String>>`, Spring thực thi qua MVC executor.
- `GET /work/callable/fail` → Callable throw exception, `@RestControllerAdvice` chuyển thành 500 JSON có mã ổn định.
- `GET /work/webtask` → `WebAsyncTask<ResponseEntity<String>>` có deadline và fallback callbacks.
- `GET /work/deferred/{id}` → chờ **POST từ request khác** để nhận kết quả.
- `POST /work/deferred/{id}/complete` → producer minh họa, gọi `setResult`.
- `DeferredResult` timeout được server hoàn thành bằng HTTP 504; `onCompletion` dọn pending map.

Ví dụ sử dụng in-memory map để dễ học; **không dùng endpoint complete công khai như production** nếu không có authentication/authorization và giới hạn pending requests.

### 10.1. Cây thư mục

```text
spring-mvc-async-models/
├── pom.xml
└── src/
    ├── main/
    │   └── java/example/
    │       ├── AsyncModelsApplication.java
    │       ├── MvcAsyncConfig.java
    │       └── WorkController.java
    └── test/
        └── java/example/WorkControllerTest.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-mvc-async-models</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
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
```

### 10.3. AsyncModelsApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncModelsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncModelsApplication.class, args);
    }
}
```

### 10.4. MvcAsyncConfig.java

```java
package example;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcAsyncConfig implements WebMvcConfigurer {

    private final AsyncTaskExecutor mvcExecutor;

    public MvcAsyncConfig(
            @Qualifier("mvcExecutor") AsyncTaskExecutor mvcExecutor) {
        this.mvcExecutor = mvcExecutor;
    }

    @Bean(name = "mvcExecutor")
    public static ThreadPoolTaskExecutor mvcExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("mvc-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.initialize();
        return executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(mvcExecutor);
        configurer.setDefaultTimeout(10_000L);
    }
}
```

Thread pool được tạo **một lần** dưới dạng Spring bean. Đây là kích thước mẫu cho demo, không phải sizing rule cho production. Nếu ứng dụng thực có task dài, cần connection pool, bounded capacity, queue metric, rejection policy và thời gian shutdown.

### 10.5. WorkController.java

```java
package example;

import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.context.request.async.WebAsyncTask;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class WorkController {

    private final Map<String, DeferredResult<ResponseEntity<String>>> pending =
            new ConcurrentHashMap<>();

    @GetMapping("/work/callable")
    public Callable<ResponseEntity<String>> callable() {
        return () -> ResponseEntity.ok("callable-ok");
    }

    @GetMapping("/work/callable/fail")
    public Callable<ResponseEntity<String>> failedCallable() {
        return () -> {
            throw new IllegalStateException("simulated failure");
        };
    }

    @GetMapping("/work/webtask")
    public WebAsyncTask<ResponseEntity<String>> webTask() {
        WebAsyncTask<ResponseEntity<String>> task =
                new WebAsyncTask<>(5_000L,
                    () -> ResponseEntity.ok("webtask-ok"));

        task.onTimeout(() ->
            ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                          .body("webtask-timeout"));

        task.onError(() ->
            ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                          .body("webtask-error"));

        task.onCompletion(() -> {
            // Chỉ ghi metric nhẹ / cleanup; không đợi tác vụ blocking.
        });

        return task;
    }

    @GetMapping("/work/deferred/{id}")
    public DeferredResult<ResponseEntity<String>> waitForWork(
            @PathVariable String id) {

        DeferredResult<ResponseEntity<String>> result =
                new DeferredResult<>(5_000L);

        DeferredResult<ResponseEntity<String>> existing =
                pending.putIfAbsent(id, result);

        if (existing != null) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT, "A waiter already exists");
        }

        result.onTimeout(() ->
            result.setResult(
                ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
                              .body("deferred-timeout")));

        result.onError(result::setErrorResult);

        result.onCompletion(() -> pending.remove(id, result));

        return result;
    }

    @PostMapping("/work/deferred/{id}/complete")
    public ResponseEntity<String> complete(
            @PathVariable String id) {

        DeferredResult<ResponseEntity<String>> result = pending.get(id);
        if (result == null) {
            return ResponseEntity.notFound().build();
        }

        boolean completed =
                result.setResult(ResponseEntity.ok("deferred-ok-" + id));

        return completed
                ? ResponseEntity.accepted().body("event-accepted")
                : ResponseEntity.status(HttpStatus.CONFLICT)
                                .body("already-completed");
    }
}

@RestControllerAdvice
class WorkErrors {
    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<Map<String, String>> onIllegalState(
            IllegalStateException exception) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of("code", "WORK_FAILED"));
    }
}
```

**Điểm cần giải thích của mã trên:**

- `Callable` và `WebAsyncTask` được MVC đưa vào `AsyncTaskExecutor`; controller chỉ tạo task và return ngay.
- `DeferredResult` không tự submit task nào. Nó đợi **POST /complete** như một sự kiện bên ngoài. Trong hệ thống thực, producer thường là message consumer hoặc callback của service.
- `pending.putIfAbsent` tránh âm thầm thay waiter có cùng ID. Không có authentication/limit trong demo: điều này **phải** được bổ sung trong production.
- Timeout set HTTP 504 theo chính sách mẫu. `setResult` có thể thất bại nếu producer đã thắng hoặc request đã hết hiệu lực.
- `onCompletion` xóa đúng pair `id/result` để không vô tình xóa một waiter mới có cùng ID.
- `result.onError(result::setErrorResult)` chuyển exception đến MVC. Callback chạy nhanh, không chặn container thread.
- `@RestControllerAdvice` xử lý exception từ Callable bị throw. Đối với lỗi network/client disconnect, không phải exception nào cũng có thể gửi response sau khi connection hỏng.

### 10.6. Chạy bằng Maven

Ở thư mục có `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

GET Callable:

```bash
curl -i http://localhost:8080/work/callable
```

Expected body khi HTTP 200:

```text
callable-ok
```

GET WebAsyncTask:

```bash
curl -i http://localhost:8080/work/webtask
```

Expected 200 body:

```text
webtask-ok
```

GET failed Callable:

```bash
curl -i http://localhost:8080/work/callable/fail
```

Expected status 500, JSON body:

```json
{"code":"WORK_FAILED"}
```

Server-side async handling không có nghĩa client nhận response “ngay”; client vẫn chờ công việc hoàn tất rồi mới có body.

### 10.7. Mô phỏng external event cho DeferredResult

Mở terminal A trước:

```bash
curl -i http://localhost:8080/work/deferred/job-42
```

Trong vòng timeout 5 giây, mở terminal B:

```bash
curl -i -X POST \
  http://localhost:8080/work/deferred/job-42/complete
```

Terminal B nhận body:

```text
event-accepted
```

Terminal A nhận body:

```text
deferred-ok-job-42
```

Nếu không có producer gửi POST, sau timeout application policy trả 504 và:

```text
deferred-timeout
```

Trên Windows PowerShell có thể dùng `curl.exe` và đưa lệnh trên một dòng. Thứ tự response headers có thể khác, không viết test assert byte-for-byte toàn bộ cURL output. Đây là demo long polling một response; production cần authentication, ownership, giới hạn concurrent waiters và giải pháp lưu trạng thái công việc nếu có nhiều instances.

## 11. Test MVC async đúng cách: hai giai đoạn

`MockMvc` không tự giả lập việc browser chờ qua network. Một async MVC test có hai lượt:

1. Gửi request bằng `mvc.perform(...)` và assert `request().asyncStarted()`.
2. Dùng `asyncDispatch(mvcResult)` để MVC xử lý concurrent result thành response, rồi assert status/body.

Mục tiêu không chỉ kiểm tra controller trả wrapper, mà kiểm tra cả **giá trị cuối cùng và exception handling**.

### 11.1. WorkControllerTest.java

File `src/test/java/example/WorkControllerTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WorkControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void callableUsesAsyncProcessing() throws Exception {
        MvcResult pending = mvc.perform(get("/work/callable"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(content().string("callable-ok"));
    }

    @Test
    void webAsyncTaskUsesAsyncProcessing() throws Exception {
        MvcResult pending = mvc.perform(get("/work/webtask"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(content().string("webtask-ok"));
    }

    @Test
    void callableExceptionIsHandledOnRedispatch() throws Exception {
        MvcResult pending = mvc.perform(get("/work/callable/fail"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code").value("WORK_FAILED"));
    }

    @Test
    void deferredResultIsCompletedByAnotherRequest()
            throws Exception {
        MvcResult waiting = mvc.perform(
                get("/work/deferred/job-test-1"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(post("/work/deferred/job-test-1/complete"))
            .andExpect(status().isAccepted())
            .andExpect(content().string("event-accepted"));

        mvc.perform(asyncDispatch(waiting))
            .andExpect(status().isOk())
            .andExpect(content().string("deferred-ok-job-test-1"));
    }

    @Test
    void unknownJobCannotBeCompleted() throws Exception {
        mvc.perform(post("/work/deferred/not-present/complete"))
            .andExpect(status().isNotFound());
    }

    @Test
    void duplicateWaiterIsRejectedWithoutReplacingOriginal()
            throws Exception {
        MvcResult waiting = mvc.perform(
                get("/work/deferred/job-test-2"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(get("/work/deferred/job-test-2"))
            .andExpect(status().isConflict());

        mvc.perform(post("/work/deferred/job-test-2/complete"))
            .andExpect(status().isAccepted());

        mvc.perform(asyncDispatch(waiting))
            .andExpect(status().isOk())
            .andExpect(content().string("deferred-ok-job-test-2"));
    }

    @Test
    void newWaiterWithAnotherIdIsIndependent()
            throws Exception {
        MvcResult a = mvc.perform(
                get("/work/deferred/job-test-3"))
            .andExpect(request().asyncStarted())
            .andReturn();

        MvcResult b = mvc.perform(
                get("/work/deferred/job-test-4"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(post("/work/deferred/job-test-4/complete"))
            .andExpect(status().isAccepted());
        mvc.perform(post("/work/deferred/job-test-3/complete"))
            .andExpect(status().isAccepted());

        mvc.perform(asyncDispatch(a))
            .andExpect(status().isOk())
            .andExpect(content().string("deferred-ok-job-test-3"));
        mvc.perform(asyncDispatch(b))
            .andExpect(status().isOk())
            .andExpect(content().string("deferred-ok-job-test-4"));
    }
}
```

Các test sử dụng ID khác nhau để không xung đột khi Spring test context dùng chung controller instance. Trong thực tế, cũng nên bảo đảm cleanup sau test và không dùng state global unbounded.

### 11.2. Vì sao chưa assert timeout bằng cách ngủ 5 giây?

Spring MVC timeout có tương tác Servlet container, async request manager và test scheduling. `Thread.sleep(5_001)` rồi hy vọng trạng thái HTTP luôn chính xác có thể tạo flaky test. Để kiểm thử timeout một cách đáng tin:

- Với unit test, tách logic timeout fallback thành hàm được test độc lập, hoặc kiểm thử interceptor/callback bằng hạ tầng mock phù hợp.
- Với integration test, chạy embedded server trên random port và giới hạn timeout nhỏ dành riêng cho test, kiểm tra phản hồi thật cùng thời gian rõ ràng.
- Trên production, quan sát tỷ lệ timeouts, cancellations và kết quả đã hoàn tất sau khi client ngắt.

Bảy test trên chủ đích xác nhận **completion model và redispatch**, không giả vờ đã kiểm chứng mọi tình huống container timeout/error. Khi cần, thêm tests riêng cho client disconnect và proxy timeouts trên môi trường triển khai thực.

## 12. Spring MVC async so với @Async, CompletableFuture và WebFlux

### 12.1. @Async không có cùng nhiệm vụ

`@Async` thuộc Spring task execution, làm một **method call** được thực thi bất đồng bộ qua proxy/executor khi áp dụng đúng. `Callable/DeferredResult/WebAsyncTask` thuộc **hợp đồng xử lý HTTP response** của Spring MVC.

Một service có `@Async` có thể được gọi từ controller, nhưng nếu controller gọi `future.get()` trước khi return, Servlet thread vẫn bị chặn. Một hướng đúng là return async type được Spring MVC hỗ trợ hoặc adapt kết quả vào `DeferredResult` mà không block.

Cần nhớ `@Async` thường dùng Spring proxy: self-invocation trong cùng object có thể không kích hoạt async advice. Không tự kết luận “method gắn @Async thì mọi call đều được tách thread”.

### 12.2. CompletableFuture / CompletionStage

Spring MVC hỗ trợ nhiều async return types thông qua async adapters, kể cả `CompletionStage`/`CompletableFuture` theo tài liệu Framework. Nếu bạn đã có một future thật từ async API, có thể tận dụng thay vì tạo extra blocking worker.

Không thực hiện:

```java
return () -> future.get();
```

nếu mục tiêu là không giữ thread để chờ một future. Cách này vẫn block worker executor; với producer đã callback-based, `DeferredResult` hoặc MVC async adapters cho `CompletionStage` phù hợp hơn.

### 12.3. MVC async không đồng nghĩa WebFlux

Spring MVC async:

- Servlet processing bắt đầu/redispatch trên container.
- Blocking JDBC/HTTP calls vẫn block worker khi chạy trong Callable.
- Khi response body được ghi trên Servlet stack, việc write có thể vẫn blocking.
- MVC có thể hỗ trợ streaming/reactive return types qua integration riêng, nhưng không biến toàn bộ HTTP layer thành WebFlux.

Spring WebFlux:

- Dựa trên reactive contracts và xử lý non-blocking I/O khi stack và dependencies tương thích.
- Thường cần rethink repository/client, backpressure và cách xử lý CPU-blocking work.
- Không phải “mọi app MVC đổi sang WebFlux sẽ nhanh hơn”; nên đo workload và khả năng sử dụng thư viện.

## 13. Những lỗi thiết kế thường gặp

| Hiểu nhầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| “Return Callable làm DB query non-blocking” | DB call vẫn block worker | Hiểu rõ thread và backend client |
| “Async response trả về ngay cho browser” | Client vẫn chờ, timeout UX không đổi | Phân biệt release Servlet thread và response completed |
| “DeferredResult tự chạy task” | Result không ai complete, timeout | Có producer/callback rõ ràng |
| “WebAsyncTask khác hoàn toàn Callable” | Thiết kế thừa lớp | WebAsyncTask chỉ bổ sung timeout/executor/callback |
| Gọi `Future#get()` trong controller | Servlet thread vẫn bị chặn | Return async type thay vì block |
| Dùng `Thread.sleep()` cho mỗi DeferredResult | Thread pool bị giữ vô ích | Chờ event thật hoặc dùng Callable hợp lý |
| Pending map không dọn | Memory leak, stale correlation IDs | `onCompletion` + timeout policy |
| Dùng `put` ghi đè waiter | Mất response của request cũ | `putIfAbsent`, duplicate policy |
| Không kiểm tra boolean `setResult` | Event đến sau timeout bị coi là thành công | Check atomic success/failure |
| Timeout callback làm việc quá lâu | Container thread bị giữ | Set fallback thật nhanh |
| Nghĩ timeout tự cancel JDBC/HTTP | Background task tiếp tục gây side effect | Downstream timeout/cancellation/idempotency |
| Không cấu hình AsyncTaskExecutor | Saturation/queue không kiểm soát | Bounded executor và metrics |
| Tạo executor mới theo request | Thread leak và overhead | Managed Spring bean |
| Dùng thread-local từ servlet trong Callable | Mất/nhầm context | Explicit propagation/task decorator |
| Nghĩ transaction của HTTP thread tự đi theo worker | Transaction không tồn tại như mong muốn | Đặt boundary ở service worker |
| Quên asyncSupported ở custom Servlet Filter | Async có thể thất bại | Đăng ký Servlet/filters tương thích |
| Quên map `DispatcherType.ASYNC` | Filter không chạy ở redispatch | Kiểm tra filter mapping/flags |
| Đếm metric mỗi interceptor preHandle | Một HTTP request bị đếm nhiều | Async-aware lifecycle/marker |
| Mặc định retry POST hoàn thành nhiều lần | Duplicate side effects | Idempotency keys, first-result-wins |
| Để public endpoint complete bất kỳ job | Người lạ hoàn tất job của user khác | Authentication, authorization, ownership |
| Hết timeout nhưng vẫn giữ request reference | Memory/resource leak | Completion cleanup, TTL, cancellation |
| Dùng MockMvc mà không `asyncDispatch` | Chỉ test stage 1, không test final response | Gọi asyncDispatch và assert status/body |
| Test timeout bằng sleep tùy ý | Flaky theo CI/container | Controlled integration testing |
| Coi Servlet MVC async = reactive non-blocking | Sai capacity plan | Chọn stack dựa trên blocking I/O thực |

## 14. Checklist lựa chọn mô hình trong production

Khi nhận một yêu cầu “endpoint phải bất đồng bộ”, nên trả lời:

1. **Kết quả do ai tạo?** Một hàm cần chạy, hay event từ producer khác?
2. **Có blocking không?** JDBC, external HTTP client, encryption/compression, file I/O?
3. **Ai sở hữu executor?** MVC executor, riêng cho workload, messaging consumer hay HTTP client event loop?
4. **Giới hạn concurrency ra sao?** Pool, queue, pending request count, per-user quota, backpressure?
5. **Timeout tổng** có phù hợp gateway, browser, HTTP client và downstream không?
6. **Response type** chỉ có một giá trị, hay nhiều events liên tục cần SSE/WebSocket?
7. **Lỗi** được đưa về `@ExceptionHandler`/fallback thế nào?
8. **Timeout** có hủy tác vụ, hay tác vụ tiếp tục? Side effects có idempotent không?
9. **Client disconnect** được quan sát và cleanup như thế nào?
10. **Context** như locale, MDC, user/tenant được truyền qua thread ra sao?
11. **Pending result** lưu ở đâu khi có nhiều replicas? In-memory map có phù hợp hay cần broker/state store?
12. **Test** đã assert `asyncStarted`, `asyncDispatch`, duplicate completion và lỗi chưa?
13. **Metrics** gồm active waiters, executor active/queue/rejections, timeout rate và p95/p99 client latency chưa?
14. **Security** đã chặn user A complete/wait job của user B chưa?
15. Có cần trả **202 Accepted + job ID** để client poll độc lập thay vì giữ HTTP long-poll request lâu không?

### 14.1. Khi nào nên trả 202 Accepted thay vì giữ request?

Nếu công việc mất nhiều phút hoặc giờ, proxy/client timeout thấp, ứng dụng có nhiều instances hoặc cần retry sau restart, endpoint thường tốt hơn khi:

```text
POST /jobs           → 202 Accepted, Location: /jobs/123
GET  /jobs/123       → trạng thái pending/running/done
GET  /jobs/123/data  → kết quả khi hoàn tất
```

Đây là mô hình **job lifecycle** bền vững; không yêu cầu giữ một DeferredResult sống nhiều phút trong memory. `DeferredResult` phù hợp hơn cho long poll vừa phải; không phải queue/job store thay thế durable messaging.

## 15. Bài tập tự kiểm tra

**1.** `Callable<T>` được ai submit vào executor?  
**Đáp án:** Spring MVC submit qua `AsyncTaskExecutor` được cấu hình.

**2.** `DeferredResult<T>` được ai complete?  
**Đáp án:** Ứng dụng/producer gọi `setResult` hoặc `setErrorResult`.

**3.** `WebAsyncTask<T>` bổ sung gì so với Callable?  
**Đáp án:** Timeout, executor lựa chọn và lifecycle callbacks.

**4.** Spring MVC async có làm browser nhận response trước khi công việc xong?  
**Đáp án:** Không; chỉ giải phóng Servlet request thread ban đầu.

**5.** Sau `Callable` return, MVC xử lý kết quả cuối cùng thế nào?  
**Đáp án:** ASYNC redispatch qua Servlet container rồi xử lý return value như MVC thông thường.

**6.** Có nên dùng DeferredResult và tạo một thread ngồi sleep chờ callback không?  
**Đáp án:** Không; mất lợi ích event-driven và tốn worker.

**7.** Khi hai producer cùng `setResult` vào một DeferredResult?  
**Đáp án:** Chỉ một winner; kiểm tra giá trị boolean và xử lý loser.

**8.** Nếu timeout trả HTTP 504, Callable có chắc ngừng chạy ngay không?  
**Đáp án:** Không; cancellation và downstream deadlines phải được thiết kế riêng.

**9.** Timeout callback của WebAsyncTask trả kiểu gì?  
**Đáp án:** `Callable<T>` tạo một giá trị thay thế có kiểu T.

**10.** Dùng `WebMvcConfigurer#configureAsyncSupport` để cấu hình gì?  
**Đáp án:** Executor, default timeout và async processing interceptors.

**11.** Khi MockMvc perform request Callable, chỉ assert 200 ngay lượt đầu có đúng không?  
**Đáp án:** Không; cần `asyncStarted()` rồi `asyncDispatch(...)`.

**12.** Nếu message broker gửi sự kiện sau timeout, có nên tiếp tục ghi response không?  
**Đáp án:** Không; `setResult` thất bại nếu result đã hết hiệu lực, cần cleanup/ignore.

**13.** `ThreadLocal` MDC có chắc xuất hiện trong Callable worker không?  
**Đáp án:** Không mặc định; cần propagation.

**14.** Spring MVC Callable có tự chuyển JDBC thành non-blocking không?  
**Đáp án:** Không.

**15.** Một request dùng ASYNC redispatch có làm controller chạy lại từ đầu không?  
**Đáp án:** MVC thường tiếp tục xử lý concurrent result, không gọi lại controller method ban đầu như request mới.

**16.** Lỗi thrown trong Callable có thể được `@ExceptionHandler` xử lý không?  
**Đáp án:** Có, qua async result exception handling.

**17.** Pending map của DeferredResult phải được dọn khi nào?  
**Đáp án:** Khi request hoàn tất vì success, timeout hoặc error; dùng `onCompletion` phù hợp.

**18.** Có nên dùng DeferredResult cho stream nhiều events?  
**Đáp án:** Không phù hợp; dùng `SseEmitter`, streaming hoặc reactive types tùy yêu cầu.

**19.** WebAsyncTask timeout được đo bắt đầu lúc nào?  
**Đáp án:** Theo async request lifecycle của Servlet/container và MVC configuration, không phải chỉ “thời gian Callable chạy trên CPU”.

**20.** Công việc nhiều phút cần survive restart nên dùng gì?  
**Đáp án:** Thường dùng durable job system + 202 Accepted/job status thay vì giữ HTTP pending vô thời hạn.

## 16. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): `Callable`, `DeferredResult`, `WebAsyncTask`, ASYNC redispatch, exceptions, interceptors, executor và context propagation.
- [Spring Framework 6.2 — DeferredResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/async/DeferredResult.html): `setResult`, `setErrorResult`, callbacks, hasResult và lifecycle.
- [Spring Framework 6.2 — WebAsyncTask Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/async/WebAsyncTask.html): timeout, executor constructors, `onTimeout`, `onError`, `onCompletion`.
- [Spring Framework 6.2 — MockMvc Async Testing](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/async-requests.html): hai bước `asyncStarted` và `asyncDispatch`.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): executor, `@Async` và cấu hình task execution.
- [Spring Framework 6.2 — Java WebMvcConfigurer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html): `configureAsyncSupport`.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/6.0/): `AsyncContext`, `asyncSupported` và Servlet dispatcher types.

**Quy tắc ghi nhớ:** nếu **Spring phải chạy một Callable để tạo kết quả**, return `Callable`; nếu muốn **timeout/executor/callback riêng** cho Callable, dùng `WebAsyncTask`; nếu **một event ngoài request tự mang kết quả đến**, dùng `DeferredResult`. Cả ba đều giải phóng Servlet thread ban đầu nhưng vẫn phải có tài nguyên xử lý, giới hạn concurrency, timeout, cleanup và bảo mật đúng cách.
