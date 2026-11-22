# Servlet async và khác biệt giữa giải phóng luồng yêu cầu với I/O không chặn trong Spring MVC

## 1. Vấn đề thực tế: request chờ lâu có nhất thiết phải chiếm Servlet thread?

Hãy hình dung `GET /api/reports/42` cần 3 giây để chờ kết quả từ một dịch vụ khác. Trong MVC đồng bộ truyền thống, thread của Servlet container nhận request, vào controller, gọi dịch vụ và **đứng chờ** trước khi ghi HTTP response. Nếu cùng lúc có nhiều request chờ I/O, số lượng request threads bận sẽ tăng, mặc dù CPU không thật sự tính toán nhiều.

Spring MVC hỗ trợ **Servlet asynchronous request processing** (Servlet 3.0+) để trả lại **thread ban đầu** cho container trong khi HTTP response **vẫn đang mở**. Kết quả sẽ được cung cấp sau qua `Callable`, `DeferredResult`, `WebAsyncTask` hoặc dạng return value tương thích. Sau đó Spring thực hiện **ASYNC dispatch** và hoàn tất response.

Tuy nhiên, có một nhầm lẫn rất phổ biến:

> **Giải phóng Servlet request thread không đồng nghĩa với việc tất cả I/O trong ứng dụng đều non-blocking.**

Nếu controller trả `Callable` mà bên trong vẫn gọi JDBC đồng bộ, thread của **executor** sẽ bị chặn trong thời gian truy vấn. Nếu ghi tệp bằng `StreamingResponseBody` với `OutputStream.write(...)`, công việc đã rời initial container thread nhưng lời gọi ghi vẫn có thể **blocking**. Cơ chế I/O không chặn ở Servlet 3.1 là tầng khác, dựa trên `ServletInputStream.isReady()`/`ReadListener` và `ServletOutputStream.isReady()`/`WriteListener`.

**Phạm vi bài:** Spring **Web MVC trên Servlet stack**, Java 17, Spring Boot 3.3.5 / Spring Framework 6.1.x; phân biệt **Servlet async**, **worker executors**, **non-blocking Servlet I/O** và **Spring WebFlux**. Bài giải thích vòng đời request, các loại return values, timeout/cancellation, cấu hình thread pool, kiểm thử MockMvc và những giới hạn về tải hệ thống.

### Kết quả cần đạt

Sau bài này, bạn có thể:

1. Mô tả request đồng bộ và Servlet async theo từng thread/dispatch.
2. Phân biệt "waiting không giữ Servlet thread" với "operation không giữ bất kỳ thread nào khi chờ".
3. Giải thích `Callable`, `DeferredResult`, `WebAsyncTask` và sự liên hệ với `CompletableFuture`.
4. Biết khi nào `ResponseBodyEmitter`, `SseEmitter`, `StreamingResponseBody` giải phóng request thread nhưng vẫn thực hiện ghi blocking.
5. Phân biệt Servlet 3.0 asynchronous request lifecycle và Servlet 3.1 non-blocking I/O callbacks.
6. Cấu hình bounded `AsyncTaskExecutor` và timeout trên Spring MVC; xử lý overload và context propagation.
7. Viết integration-style controller và MockMvc async tests, quan sát khác biệt giữa `REQUEST` và `ASYNC dispatch`.
8. Quyết định khi nào giữ Spring MVC và khi nào xem xét WebFlux hoặc driver/client thực sự non-blocking.

## 2. Bốn khái niệm cần tách riêng

| Khái niệm | Nó giải quyết điều gì? | Có làm JDBC/HTTP client blocking thành non-blocking không? |
| --- | --- | --- |
| **Servlet request thread** | Thread container đang xử lý filter/servlet/controller cho một dispatch | Không |
| **Servlet async lifecycle** | Cho phép thread initial request thoát trong khi response còn mở, sau đó dispatch lại | Không |
| **Async executor / worker pool** | Thực thi công việc ở thread khác, có thể là các blocking calls | Không |
| **Non-blocking I/O** | I/O readiness/callback/async client; thread không phải đợi socket sẵn sàng bằng cách block | Chỉ khi cả API/driver/pipeline thực sự hỗ trợ |

Ví dụ đồng bộ:

```text
Servlet thread (http-nio-8080-exec-1)
  nhận request -> filter -> controller
  -> blocking HTTP call / JDBC (chờ 3 giây)
  -> serialize JSON -> ghi response -> kết thúc
  [thread bị chiếm suốt thời gian chờ]
```

Ví dụ `Callable`:

```text
Servlet thread (http-nio-8080-exec-1)
  nhận request -> controller trả Callable
  -> request.startAsync()
  -> thoát filter/servlet chain, trả thread về pool

MVC worker thread (mvc-work-1)
  chạy Callable -> blocking JDBC/HTTP call (chờ 3 giây)
  -> tạo Java result -> báo kết quả

Servlet container thread (có thể là thread khác)
  xử lý ASYNC dispatch
  -> MVC serialize result -> ghi HTTP response -> kết thúc
```

Trong ví dụ thứ hai, **container thread ban đầu được giải phóng**, nhưng vẫn có **mvc-work-1** bị block. Vì vậy lợi ích chủ yếu là **tách tài nguyên thread container khỏi công việc lâu** và kiểm soát pool/chính sách riêng, không phải tạo phép màu biến ứng dụng thành I/O non-blocking.

Ví dụ `DeferredResult` đợi một external event/callback thực sự non-blocking:

```text
Servlet thread -> trả DeferredResult -> startAsync -> thoát
                        |
                        | request đang pending, chưa có result
                        | không bắt buộc có worker thread ngủ chờ
                        v
External callback/event loop nhận kết quả sau đó
  -> deferredResult.setResult(value)
                        |
                        v
Servlet ASYNC dispatch -> ghi HTTP response -> complete
```

Nếu bạn triển khai DeferredResult bằng `new Thread(() -> Thread.sleep(...))` cho mỗi request, bạn vẫn tiêu thụ một thread, chỉ là thread khác. **DeferredResult tự nó không làm producer non-blocking.**

## 3. Từ Servlet 3.0: startAsync(), AsyncContext và ASYNC dispatch

Servlet 3.0 bổ sung asynchronous request processing. Ở tầng Servlet API, ý tưởng là:

```java
AsyncContext asyncContext = request.startAsync();
// Có thể đăng ký listener, timeout hoặc trigger công việc ngoài thread này.
// Khi kết quả sẵn sàng: asyncContext.dispatch() hoặc asyncContext.complete().
```

Đây là **snippet Servlet-level**; `request` là `HttpServletRequest` trong Servlet hỗ trợ async, import `jakarta.servlet.AsyncContext`. Không đặt trực tiếp đoạn này vào method MVC vốn đã trả `Callable`/`DeferredResult` rồi cố điều khiển lifecycle song song: **Spring MVC quản lý startAsync/dispatch/complete cho bạn**.

### 3.1. Vòng đời asynchronous request trong Spring MVC

Giả sử endpoint trả `DeferredResult`:

1. Container nhận HTTP request và cấp một Servlet thread.
2. DispatcherServlet chạy handler mapping, binding, interceptors và controller.
3. Controller tạo `DeferredResult` rồi **return sớm**, chưa có body kết quả.
4. MVC gọi cơ chế Servlet `request.startAsync()` và thoát filter/servlet chain.
5. Container thread initial request trở lại pool; response **chưa bị commit/close**.
6. Một thread/callback khác hoàn thành `DeferredResult.setResult(value)` hoặc `setErrorResult(...)`.
7. MVC yêu cầu **ASYNC dispatch** tới Servlet container.
8. DispatcherServlet được gọi lại trong dispatch mới; nó dùng **concurrent result** đã có, **không gọi lại business controller method từ đầu** để tạo result lần hai.
9. MVC áp dụng return-value handling/message converter và ghi response; async processing được complete.
10. Timeout, client disconnect, exceptions và async listeners có thể can thiệp vào flow trên.

```text
HTTP Request
    |
    v
REQUEST dispatch (Servlet thread #1)
    |
    v
Spring MVC controller -> DeferredResult / Callable
    |
    v
Servlet startAsync(); request thread #1 released
    |
    +--------------------- waiting --------------------+
    |                                                  |
    |           producer event / worker result          |
    |                      arrives                     |
    +--------------------------+-----------------------+
                               |
                               v
                  DeferredResult.setResult(...)
                               |
                               v
ASYNC dispatch (Servlet thread #2, may equal #1)
                               |
                               v
           Spring MVC return-value handling + response
                               |
                               v
                       Request complete
```

**Không giả định dispatch thứ hai dùng cùng thread**: container có quyền dùng một thread khác. Tương tự, `@RequestScope`, MDC, SecurityContext, transaction-bound state và những `ThreadLocal` custom **không tự lan truyền** qua mọi worker/dispatch; xem mục 12.

### 3.2. Servlet async phải được bật ở đâu?

Để cơ chế hoạt động, Servlet/filter chain tương ứng phải hỗ trợ asynchronous processing:

- Servlet cần `asyncSupported=true`.
- Các filters trên đường xử lý không được chặn async và cần dispatcher mappings thích hợp (`jakarta.servlet.DispatcherType.ASYNC`) khi phải hoạt động trên async redispatch.
- Với Spring Boot embedded Servlet container và Spring MVC auto-configuration phổ biến, nhiều khai báo được cấu hình sẵn phù hợp.
- Nếu đăng ký filters/servlets thủ công, sử dụng `FilterRegistrationBean.setAsyncSupported(true)` hoặc Servlet 3.x registration tương ứng theo kiến trúc.
- Khi cần filter chạy lại ở dispatch `ASYNC`, đảm bảo mapping bao gồm dispatch type này; nhưng đừng đơn giản chạy mọi filter logic hai lần mà không xét semantics.

Một lỗi thường thấy:

```text
java.lang.IllegalStateException:
Async support must be enabled on a servlet and for all filters involved...
```

Thông báo cụ thể tùy container/framework. Nó thường liên quan filter hoặc servlet không hỗ trợ async, không phải do return type `Callable` sai.

### 3.3. Vì sao ASYNC dispatch quan trọng?

Spring MVC không chỉ nhận giá trị từ thread ngoài rồi viết trực tiếp như thể vẫn ở request ban đầu. Redispatch giúp tái sử dụng pipeline MVC để xử lý body, status, converters và error handling theo lifecycle thống nhất.

Các lifecycle callbacks trong `HandlerInterceptor` cần hiểu async: `afterConcurrentHandlingStarted(...)` của `AsyncHandlerInterceptor` chạy khi request chuyển sang async; `postHandle`/`afterCompletion` trong initial dispatch không luôn xảy ra theo thứ tự như request sync. Tại subsequent dispatch, phần xử lý MVC tiếp tục và completion được gọi theo lifecycle. Nếu dùng timing/trace interceptors, cần chống log đôi và cleanup chưa đúng.

## 4. Spring MVC có những kiểu return value async nào?

### 4.1. Callable<T>: chuyển tác vụ sang MVC async executor

```java
@GetMapping("/price")
public Callable<ResponseEntity<PriceDto>> price() {
    return () -> {
        PriceDto dto = blockingPriceService.loadPrice();
        return ResponseEntity.ok(dto);
    };
}
```

Đây là **snippet** với `PriceDto` và `blockingPriceService` giả định đã tồn tại; không phải controller runnable độc lập. Khi controller trả Callable, MVC bắt đầu Servlet async, rồi gửi Callable tới `AsyncTaskExecutor`. Trong Callable, các thao tác blocking vẫn **chiếm worker thread**. Khi Callable trả kết quả, Spring redispatch và hoàn tất.

**Phù hợp khi:**
- Bạn có business logic lâu hoặc blocking mà cần tách khỏi Servlet threads.
- Muốn dùng executor riêng với queue/pool size đã cấu hình.
- Kết quả trả một lần, không phải stream vô hạn.

**Không phù hợp để tuyên bố "không có thread chờ"** nếu Callable gọi `Thread.sleep`, JDBC blocking, file I/O blocking hoặc sync REST client.

### 4.2. DeferredResult<T>: hoàn tất từ sự kiện bên ngoài

```java
@GetMapping("/status")
public DeferredResult<ResponseEntity<StatusDto>> status() {
    DeferredResult<ResponseEntity<StatusDto>> result =
            new DeferredResult<>(5000L);

    queue.registerListener(event -> {
        result.setResult(ResponseEntity.ok(new StatusDto(event.state())));
    });

    result.onTimeout(() ->
            result.setErrorResult(
                ResponseEntity.status(503).build()));

    result.onCompletion(() -> queue.unregisterListener(result));
    return result;
}
```

Đây là **pseudocode Java dạng snippet** vì `queue`, `StatusDto` và event API không được khai báo, đồng thời `unregisterListener` ở hệ thống thật phải dùng chính registration token/listener phù hợp. Ý nghĩa là kết quả có thể đến từ message broker callback, non-blocking HTTP client callback hoặc event stream, **không cần tạo một thread ngủ chờ cho mỗi request**.

- `setResult(T)`: cung cấp kết quả để MVC redispatch.
- `setErrorResult(Object)`: cung cấp exception hoặc error result để MVC xử lý.
- `onTimeout(Runnable)`: xử lý khi container báo thời gian chờ async đã hết.
- `onError(Consumer<Throwable>)`: phản ứng với lỗi async.
- `onCompletion(Runnable)`: giải phóng resources/registrations sau khi request kết thúc.

**Lưu ý vòng đời:** `setResult` có thể thất bại/không còn tác dụng khi result đã được set bởi timeout/error; không đợi đến khi HTTP response đóng rồi tiếp tục gửi. Khi dùng queue/listener, cleanup trên completion/cancel/timeout để tránh memory leak.

### 4.3. WebAsyncTask<T>: Callable với cấu hình riêng

`WebAsyncTask` là wrapper của Callable, có thể chỉ định timeout, executor và callbacks cho một endpoint:

```java
@GetMapping("/report")
public WebAsyncTask<ResponseEntity<String>> report() {
    WebAsyncTask<ResponseEntity<String>> task =
        new WebAsyncTask<>(3000L,
            () -> ResponseEntity.ok("ready"));

    task.onTimeout(() ->
        ResponseEntity.status(503).body("timed out"));
    return task;
}
```

Snippet này có thể đặt trong `@RestController` với imports `GetMapping`, `ResponseEntity`, `WebAsyncTask`. Timeout `3000L` tính theo milliseconds. `WebAsyncTask` **không tự biến Callable thành non-blocking I/O**; công việc vẫn chạy trên executor.

### 4.4. CompletionStage/CompletableFuture

Spring MVC có thể nhận các async single-value return types như `CompletionStage`/`CompletableFuture` qua return-value adaptation:

```java
@GetMapping("/remote")
public CompletableFuture<ResponseEntity<String>> remote() {
    return service.fetchAsync()
            .thenApply(ResponseEntity::ok);
}
```

Đây là snippet vì `service.fetchAsync()` chưa khai báo. Lợi ích phụ thuộc implementation của `fetchAsync()`:

- Nếu nó dùng HTTP client async thật sự, thời gian chờ mạng có thể không chiếm một worker thread riêng.
- Nếu nó dùng `CompletableFuture.supplyAsync(() -> blockingService.call())`, có worker thread bị block trong `call()`.
- Nếu dùng `supplyAsync` mà không chỉ định executor, mặc định có thể dùng common ForkJoinPool — **không nên mặc định đó là thread pool phù hợp cho blocking công việc production**.

Không đánh giá non-blocking chỉ dựa vào signature `CompletableFuture`.

### 4.5. StreamingResponseBody, ResponseBodyEmitter và SseEmitter

| Loại | Dùng để làm gì | Có chắc non-blocking socket I/O không? |
| --- | --- | --- |
| `StreamingResponseBody` | Ghi raw bytes dần ra `OutputStream`, ví dụ large download | **Không.** MVC dùng thread thực thi task; `write` có thể blocking |
| `ResponseBodyEmitter` | Gửi nhiều đối tượng/phần response theo thời gian thông qua converters | **Không bảo đảm.** Việc ghi Servlet response có thể blocking |
| `SseEmitter` | Server-Sent Events (`text/event-stream`) trên HTTP kết nối lâu | Không biến transport/write pipeline thành fully non-blocking |
| `Callable` | Một kết quả được tạo trong executor | Worker có thể block |
| `DeferredResult` | Một kết quả do producer/event hoàn tất | Phụ thuộc producer, có thể không cần thread chờ |

Với SSE, cần heartbeat, timeout, client disconnect, cleanup subscriptions và policy giới hạn concurrent connections. Kết nối còn mở vẫn tiêu thụ socket descriptors, buffers, server state và tài nguyên khác dù initial Servlet thread đã được giải phóng.

## 5. Servlet 3.1: I/O không chặn thật sự là tầng khác

Servlet **3.0 asynchronous request lifecycle** giải phóng request thread trong lúc chờ result. Servlet **3.1 non-blocking I/O** thêm APIs để đọc/ghi khi stream sẵn sàng, thay vì block thread ở socket I/O:

- `ServletInputStream.isReady()` / `isFinished()` / `setReadListener(ReadListener)`.
- `ServletOutputStream.isReady()` / `setWriteListener(WriteListener)`.
- `ReadListener.onDataAvailable()`, `onAllDataRead()`, `onError(...)`.
- `WriteListener.onWritePossible()` và `onError(...)`.

### 5.1. Blocking I/O

Với OutputStream thông thường:

```java
// Snippet trong một Servlet/synchronous code path.
OutputStream out = response.getOutputStream();
out.write(bigChunk); // Có thể BLOCK đến khi đủ buffer/network capacity.
```

Khi client đọc rất chậm hoặc network buffer đầy, `write` có thể block một thread đang gọi. Chuyển đoạn này vào một `StreamingResponseBody` worker **không thay đổi bản chất blocking** của `write`.

### 5.2. Non-blocking output readiness

Với API Servlet 3.1, mô hình đúng là:

```text
request vào Servlet có async support
  -> startAsync()
  -> getOutputStream().setWriteListener(...)
  -> callback onWritePossible()
       while (output.isReady() && còn bytes):
           write phần có thể ghi
       nếu output không ready: THOÁT callback, không busy-spin
  -> container gọi lại onWritePossible() khi sẵn sàng
  -> khi ghi xong: asyncContext.complete()
```

Snippet minh họa các lời gọi:

```java
ServletOutputStream output = response.getOutputStream();

output.setWriteListener(new WriteListener() {
    @Override
    public void onWritePossible() throws IOException {
        while (output.isReady() && hasPendingBytes()) {
            writeNextChunk(output);
        }
        if (allBytesWritten()) {
            asyncContext.complete();
        }
    }

    @Override
    public void onError(Throwable error) {
        handleFailure(error);
        asyncContext.complete();
    }
});
```

Đây là **pseudocode định hướng**: `hasPendingBytes`, `writeNextChunk`, `allBytesWritten`, `handleFailure` và `asyncContext` phải được tự triển khai và đồng bộ hóa, không phải class runnable sẵn. Cần tránh gọi `complete()` nhiều lần, xử lý lỗi/partial writes và tránh block trong callbacks. Đầu vào tương tự dùng `ReadListener` và vòng lặp `while(input.isReady() && !input.isFinished())`.

**Điều kiện quan trọng:** callbacks phải tôn trọng readiness, không gọi I/O trái contract, không cố spin khi `isReady()==false`. I/O non-blocking ở đây giải quyết việc thread bị block bởi **network stream readiness**, nhưng application callbacks vẫn có thể block nếu bạn gọi JDBC blocking ở trong chúng.

### 5.3. So sánh hai cơ chế bằng câu ngắn

- `request.startAsync()`: "Tôi rời Servlet thread hiện tại, giữ HTTP exchange sống và sẽ tiếp tục sau."
- `ServletOutputStream.setWriteListener(...)`: "Hãy gọi tôi khi socket output có thể ghi; tôi không cần thread đứng chờ buffer trống."
- `Callable`: "Hãy chạy logic này trên worker, thường vẫn synchronous/blocking bên trong."
- `DeferredResult`: "Tôi sẽ cung cấp kết quả khi producer bên ngoài báo xong; không cần worker riêng đứng chờ nếu producer là event-driven."
- `WebFlux + non-blocking client/driver`: "Cả pipeline có thể theo readiness/signals và backpressure thay vì dùng một thread chờ trên mỗi blocking operation", **với điều kiện không nhúng blocking calls vào event-loop**.

Không đồng nhất **asynchronous API** với **non-blocking implementation**.

## 6. So sánh các mô hình theo thread consumption

Giả sử có 100 HTTP requests cùng lúc, mỗi request phải chờ 2 giây một remote service. Đây là **ví dụ tư duy**, không phải benchmark hay số liệu throughput.

| Cách viết | Servlet thread initial request | Trong lúc chờ remote |
| --- | --- | --- |
| Controller sync + blocking client | Giữ thread đến lúc hoàn tất | **Servlet thread** chờ |
| Controller trả Callable + blocking client | Giải phóng sớm | **Executor worker thread** chờ |
| DeferredResult + executor chạy blocking client | Giải phóng sớm | **App worker thread** chờ |
| DeferredResult + HTTP client event-driven non-blocking | Giải phóng sớm | Không cần một worker đứng chờ từng request; vẫn có event-loop/runtime threads |
| Servlet 3.1 WriteListener | Giải phóng khi socket output chưa sẵn sàng | Container callbacks khi có thể ghi, nếu code tuân contract |
| Spring WebFlux + end-to-end reactive I/O | Mô hình khác, thường event-driven | Ít thread cho nhiều kết nối chờ, nếu các dependencies không block |

**Không suy ra** "100 requests async = 0 threads". Dù waiting không có thread riêng, server vẫn cần thread xử lý callback, CPU, serialization, dispatch, GC, network stack; còn cần memory cho mỗi pending request, sockets và timeout state.

Nếu JDBC driver chỉ cung cấp blocking API, dùng WebFlux hoặc CompletableFuture cũng không tự biến JDBC thành non-blocking. Có thể offload blocking call lên bounded scheduler/executor, nhưng đó vẫn là **thread chuyển nơi block**, không phải non-blocking driver.

## 7. Demo hoàn chỉnh: Java 17 + Spring Boot 3.3.5 + Spring MVC async

Demo có bốn endpoint:

- `GET /api/async/sync`: trả kết quả đồng bộ, thread là Servlet container thread.
- `GET /api/async/callable`: trả `Callable` và ghi nhận tên worker thread `mvc-work-*`.
- `GET /api/async/deferred`: trả `DeferredResult`; producer chạy trong thread pool `producer-*`; dùng callback hoàn thành.
- `GET /api/async/web-task`: dùng `WebAsyncTask` để gắn timeout cho một Callable.

**Lưu ý:** Demo không chờ remote service thật và không cố tình `Thread.sleep`. Mục tiêu là kiểm chứng **lifecycle/executor**, không chứng minh latency hoặc throughput khi hệ thống có tải. DeferredResult của demo vẫn có worker producer để tạo dữ liệu; nó **không phải** ví dụ producer non-blocking end-to-end.

### 7.1. Cấu trúc project

```text
servlet-async-demo/
├── pom.xml
└── src/
    ├── main/java/example/asyncmvc/
    │   ├── AsyncMvcApplication.java
    │   ├── AsyncMvcConfig.java
    │   └── AsyncDemoController.java
    └── test/java/example/asyncmvc/
        └── AsyncDemoControllerTest.java
```

**`pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>servlet-async-demo</artifactId>
    <version>1.0.0</version>
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

Dự án chỉ cần web starter cho MVC, Jackson và embedded Servlet container; thêm starter-test để chạy MockMvc/JUnit. Không cần WebFlux, không cần Reactor và không cần thư viện reactive để dùng Servlet async.

**`src/main/java/example/asyncmvc/AsyncMvcApplication.java`:**

```java
package example.asyncmvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncMvcApplication.class, args);
    }
}
```

### 7.2. Đăng ký bounded executor và timeout

Đối với `Callable`, Spring MVC có một `AsyncTaskExecutor`. Nếu không cấu hình pool phù hợp, default executor của MVC không phải lựa chọn production dưới tải. Cấu hình:

**`src/main/java/example/asyncmvc/AsyncMvcConfig.java`:**

```java
package example.asyncmvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AsyncMvcConfig implements WebMvcConfigurer {

    @Bean("mvcAsyncExecutor")
    public ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("mvc-work-");
        pool.setWaitForTasksToCompleteOnShutdown(true);
        pool.setAwaitTerminationSeconds(5);
        return pool;
    }

    @Bean("producerExecutor")
    public ThreadPoolTaskExecutor producerExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(16);
        pool.setThreadNamePrefix("producer-");
        pool.setWaitForTasksToCompleteOnShutdown(true);
        pool.setAwaitTerminationSeconds(5);
        return pool;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(mvcAsyncExecutor());
        configurer.setDefaultTimeout(5000L);
    }
}
```

Giải thích:

- `mvcAsyncExecutor` chạy `Callable`/`WebAsyncTask` và là MVC async executor. `setDefaultTimeout(5000L)` áp dụng mặc định khi return type không override.
- `producerExecutor` minh họa **executor do ứng dụng quản lý**, dùng để hoàn tất `DeferredResult`. `DeferredResult` không nhất thiết chạy trên pool `mvcAsyncExecutor` — producer nằm ở đâu là quyết định của app.
- `corePoolSize`, `maxPoolSize`, `queueCapacity` đặt giới hạn có ý nghĩa. Khi pool/queue đều đầy, task có thể bị reject. **Không tạo pool không giới hạn hoặc queue vô hạn chỉ vì muốn requests "async".**
- `threadNamePrefix` giúp nhận diện thread trong logs và tests. Tên thread không phải API contract của production clients, chỉ là công cụ minh họa.
- Spring quản lý lifecycle của `ThreadPoolTaskExecutor` beans, bao gồm khởi tạo và shutdown.
- Gọi `mvcAsyncExecutor()` từ một `@Configuration` được proxy bởi Spring theo default `proxyBeanMethods=true` sẽ lấy cùng singleton bean; không phải tự tạo thread pool mới mỗi request.

**Quan trọng về capacity:** Khi pool có bounded queue, `maxPoolSize` thường chỉ được dùng sau khi queue đã đạt giới hạn (tùy executor behavior). Nếu job chạy lâu, queue có thể tăng request latency; cần đo **active threads, queued tasks, rejected tasks, request timeout, p95/p99 latency** thay vì chỉ tăng pool size.

### 7.3. Controller: sync, Callable, DeferredResult, WebAsyncTask

**`src/main/java/example/asyncmvc/AsyncDemoController.java`:**

```java
package example.asyncmvc;

import java.util.concurrent.Callable;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.context.request.async.WebAsyncTask;

@RestController
@RequestMapping("/api/async")
public class AsyncDemoController {

    public record Reply(String mode, String thread) {}

    private final ThreadPoolTaskExecutor producerExecutor;

    public AsyncDemoController(
            @Qualifier("producerExecutor")
            ThreadPoolTaskExecutor producerExecutor) {
        this.producerExecutor = producerExecutor;
    }

    @GetMapping("/sync")
    public ResponseEntity<Reply> synchronous() {
        return ResponseEntity.ok(
                new Reply("sync", Thread.currentThread().getName()));
    }

    @GetMapping("/callable")
    public Callable<ResponseEntity<Reply>> callable() {
        return () -> ResponseEntity.ok(
                new Reply("callable", Thread.currentThread().getName()));
    }

    @GetMapping("/deferred")
    public DeferredResult<ResponseEntity<Reply>> deferred() {
        DeferredResult<ResponseEntity<Reply>> result =
                new DeferredResult<>(4000L);

        result.onTimeout(() -> result.setErrorResult(
                ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                        .body(new Reply("timeout", "none"))));

        result.onError(error -> result.setErrorResult(
                ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                        .body(new Reply("error", "none"))));

        try {
            producerExecutor.execute(() -> {
                Reply reply = new Reply(
                        "deferred", Thread.currentThread().getName());
                result.setResult(ResponseEntity.ok(reply));
            });
        } catch (RuntimeException rejected) {
            // Demo: khi pool không nhận công việc, trả lỗi có kiểm soát.
            result.setErrorResult(
                    ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                            .body(new Reply("overloaded", "none")));
        }

        return result;
    }

    @GetMapping("/web-task")
    public WebAsyncTask<ResponseEntity<Reply>> webTask() {
        WebAsyncTask<ResponseEntity<Reply>> task =
                new WebAsyncTask<>(3000L, () ->
                        ResponseEntity.ok(new Reply(
                                "web-task",
                                Thread.currentThread().getName())));

        task.onTimeout(() ->
                ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                        .body(new Reply("timeout", "none")));

        return task;
    }
}
```

**Tại sao code này hợp lý để học Servlet async?**

1. `synchronous()` thực thi trên Servlet request thread; return body cùng dispatch.
2. `callable()` trả closure; Spring bắt đầu async và thực thi closure trên pool `mvc-work-*`; response được hoàn tất trong một ASYNC dispatch.
3. `deferred()` trả **một promise do ứng dụng điều khiển**. Work được gửi tới `producerExecutor`; khi hoàn tất gọi `setResult` để MVC redispatch. Nếu producer này thay bằng callback thật của non-blocking I/O, có thể không cần thread đứng chờ cho mỗi HTTP call.
4. `webTask()` minh họa per-request timeout 3s với Callable. `WebAsyncTask` phù hợp khi endpoint cần callback timeout riêng.
5. `onTimeout` và `onError` trả response status cụ thể qua `setErrorResult`. Chúng không bảo đảm sửa được response nếu đã commit một phần hoặc socket client đã đóng.
6. `ThreadPoolTaskExecutor.execute(...)` có thể từ chối task khi overload; demo bắt RuntimeException khi submit để tránh pending forever. Trong hệ thống thật, nên bắt **đúng exception rejection policy** và tránh che lỗi lập trình khác; ví dụ có chủ ý tối giản.
7. Tên `producer-*` trong JSON cho biết **producer thread**, không phải Servlet thread ghi cuối cùng.
8. Không có `Thread.sleep`, network request hay database, nên ví dụ chỉ xác nhận lifecycle chứ không chứng minh hiệu năng.
9. Một `DeferredResult` đã timeout có thể từ chối result đến muộn; code production phải kiểm tra return value của `setResult` nếu cần cleanup/metrics.
10. Không gọi `request.startAsync()` trực tiếp: Spring MVC tự quản lý lifecycle khi return kiểu async.

**Lưu ý về timeout:** `DeferredResult(4000L)` và `WebAsyncTask(3000L)` dùng timeout theo milliseconds; trong Servlet async, timeout tính sau khi thread initial request thoát và request chuyển vào trạng thái chờ. Runtime thực có thể có proxy/ingress timeout ngắn hơn; không coi server-side timeout là một deadline tuyệt đối đến từng millisecond trên toàn mạng.

### 7.4. Chạy demo

Từ thư mục `servlet-async-demo` có `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Đây là **hai lệnh chạy tuần tự**. Cài JDK 17+ và Maven. Với Boot default, ứng dụng chạy tại `http://localhost:8080`.

Các yêu cầu:

```bash
curl -i 'http://localhost:8080/api/async/sync'
curl -i 'http://localhost:8080/api/async/callable'
curl -i 'http://localhost:8080/api/async/deferred'
curl -i 'http://localhost:8080/api/async/web-task'
```

Ví dụ response bodies có dạng:

```json
{"mode":"sync","thread":"http-nio-8080-exec-1"}
```

```json
{"mode":"callable","thread":"mvc-work-1"}
```

```json
{"mode":"deferred","thread":"producer-1"}
```

```json
{"mode":"web-task","thread":"mvc-work-2"}
```

**Đây là kết quả minh họa**, không cam kết tên/số cuối thread. Số thread, thứ tự thread creation, và trường hợp pool reuse phụ thuộc runtime/độ đồng thời. Với các request thành công bình thường, status dự kiến là `200 OK`. Response body `thread` chỉ là bằng chứng công việc đã chạy ở loại pool khác, không phải bằng chứng toàn bộ socket/network operations non-blocking.

## 8. MockMvc: kiểm tra asyncStarted và asyncDispatch

Nếu test chỉ gọi `mvc.perform(get("/api/async/callable")).andExpect(status().isOk())` ngay ở lần dispatch đầu, kết quả có thể chưa sẵn sàng vì request đang async. MockMvc cung cấp:

- `request().asyncStarted()`: xác nhận controller đã chuyển sang asynchronous handling.
- `MvcResult` từ initial request: giữ request/response để tiếp tục.
- `asyncDispatch(mvcResult)`: mô phỏng subsequent Servlet ASYNC dispatch khi kết quả sẵn sàng.
- `jsonPath`/`status`: kiểm tra response **sau** dispatch.

**`src/test/java/example/asyncmvc/AsyncDemoControllerTest.java`:**

```java
package example.asyncmvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncDemoControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void synchronousResponseIsImmediate() throws Exception {
        mvc.perform(get("/api/async/sync"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.mode").value("sync"));
    }

    @Test
    void callableStartsAsyncAndRunsOnMvcExecutor()
            throws Exception {
        MvcResult pending = mvc.perform(get("/api/async/callable"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.mode").value("callable"))
           .andExpect(jsonPath("$.thread").value(
                   startsWith("mvc-work-")));
    }

    @Test
    void deferredResultUsesProducerExecutor()
            throws Exception {
        MvcResult pending = mvc.perform(get("/api/async/deferred"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.mode").value("deferred"))
           .andExpect(jsonPath("$.thread").value(
                   startsWith("producer-")));
    }

    @Test
    void webAsyncTaskUsesMvcExecutor()
            throws Exception {
        MvcResult pending = mvc.perform(get("/api/async/web-task"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.mode").value("web-task"))
           .andExpect(jsonPath("$.thread").value(
                   startsWith("mvc-work-")));
    }
}
```

Chạy:

```bash
mvn test
```

Bộ test có **4 test methods**. Nếu pass, Maven kết thúc exit code `0` và thường in summary `Tests run: 4, Failures: 0, Errors: 0, Skipped: 0`. Ví dụ này kiểm tra return-value lifecycle bằng MockMvc; không phải một phép đo độ trễ hoặc I/O readiness của real socket. Không khẳng định đã chạy Maven trong quá trình tạo tài liệu này.

### Vì sao không assert thread đầu tiên == thread sau redispatch?

Spring/container có thể dùng các thread khác nhau cho initial request, task executor và redispatch. Thread names từ response ở demo ghi nhận lúc business reply được tạo, **không chứng minh** thread ghi HTTP response. Vì vậy test chỉ kiểm tra prefix phù hợp với producer/Callable executor, không bắt các thread IDs phải bằng nhau.

### Test timeout như thế nào?

Để test timeout callback thật, MockMvc đơn thuần có thể không kích hoạt giống hệt container network timeouts. Có thể dùng `MockAsyncContext` hoặc integration test qua embedded Tomcat và một producer được điều khiển bởi `CountDownLatch`/fake service, nhưng không nên dùng `Thread.sleep(10000)` trong unit tests rồi cho rằng timeout chắc chắn ổn định.

Một test đáng tin nên chủ động điều khiển thời điểm producer hoàn thành và timeout, kiểm chứng status/error body theo chính sách ứng dụng. Cần kiểm tra chuyện công việc tiếp tục chạy sau HTTP timeout và có được cancel hay không. `DeferredResult.onTimeout` không tự gọi `Future.cancel(true)` trên task bạn submit.

## 9. Timeout, lỗi và client disconnect

Async request để response pending nên có **timeout policy**, cả ở MVC lẫn proxy/network. Nếu không, kết nối mở quá lâu có thể tích tụ state và sockets.

### 9.1. Timeout không đồng nghĩa cancellation

Khi request timeout:

1. Container có thể báo async timeout.
2. Spring MVC/interceptor/`DeferredResult.onTimeout` có cơ hội tạo error result.
3. MVC cố redispatch để ghi response lỗi, nếu HTTP response chưa commit và client còn kết nối.
4. **Blocking service/worker task đang chạy không nhất thiết bị dừng**. Bạn phải có deadline và cancellation policy ở producer/driver.

Nếu chạy `Callable` gọi sync REST client timeout 60 giây nhưng MVC timeout 3 giây, request phía client có thể nhận 503 sau 3 giây trong khi worker vẫn chạy/đợi tới timeout 60 giây. Khi đủ nhiều tasks, pool vẫn cạn dù container threads rảnh.

**Quy tắc thực hành:** request deadline phải được truyền tới downstream I/O: connection/read timeout, database statement timeout, client cancellation, messaging subscription cleanup, queue cancellation. Không chỉ đặt `configureAsyncSupport.setDefaultTimeout(...)` rồi coi việc quản lý tải đã xong.

### 9.2. Exception propagation

- Với `Callable` ném exception, Spring MVC có thể xử lý kết quả lỗi qua exception resolvers/`@ControllerAdvice` trong redispatch.
- Với `DeferredResult`, dùng `setErrorResult(exception)` hoặc một error result phù hợp; Spring MVC redispatch và xử lý theo return type/exception.
- Nếu response đã ghi một phần (streaming) hoặc client ngắt kết nối, không thể chắc chắn thay HTTP status/body nữa. Log/metrics phải phân biệt lỗi nghiệp vụ với broken pipe/timeout/client abort.
- Không expose stack trace, database error hay credentials trong error response. Dùng stable error codes và request correlation ID.

### 9.3. Error callbacks và cleanup

`DeferredResult` có:
- `onTimeout(...)` để trả fallback/error.
- `onError(...)` để phản ứng exception.
- `onCompletion(...)` để dọn subscription, pending listener registration, slot trong long-polling map, timer/correlation context.

Cần tránh race giữa producer completion và timeout. `setResult(...)` trả boolean cho biết kết quả có được set hay không; chỉ callback đầu tiên thành công được dùng. Dùng `AtomicBoolean`/state machine khi cleanup nhiều nguồn có thể chạy đồng thời.

Một `DeferredResult` lưu trong `ConcurrentHashMap` để đợi sự kiện cần bị xóa khi complete/timeout, tránh memory leak nếu client bỏ đi hoặc producer không bao giờ có event.

## 10. Tại sao @Async không đồng nghĩa HTTP Servlet async?

Spring `@Async` thường đánh dấu method bean chạy ở task executor khác, và trả `Future`/`CompletableFuture` hoặc `void`. Nó là **method invocation async**, không phải bản thân Servlet request lifecycle:

```java
@Async
public CompletableFuture<String> loadReport() {
    return CompletableFuture.completedFuture(
            blockingRepository.loadReport());
}
```

Đây là snippet có `blockingRepository` giả định; dù trả CompletableFuture, gọi `blockingRepository.loadReport()` vẫn block thread mà method `@Async` chạy trên đó. Muốn controller release initial request thread, return type MVC phải được xử lý như async return value, hoặc controller chọn cơ chế `DeferredResult`/`Callable`. Một method tự gọi trên cùng bean (**self-invocation**) có thể bypass `@Async` proxy, nên không mặc định annotation sẽ đổi thread.

**Không nên** tạo mới một raw thread trên mỗi HTTP request:

```java
// PHẢN VÍ DỤ: không nên sinh unbounded threads theo request.
new Thread(() -> doBlockingWork()).start();
```

Với load lớn, việc không bound concurrency gây OOM, context switching và khó shutdown. Dùng executor bounded, queue policy, service-level timeouts và capacity planning.

## 11. StreamingResponseBody: stream không đồng nghĩa non-blocking

Ví dụ trả bytes qua `StreamingResponseBody`:

```java
@GetMapping("/download")
public StreamingResponseBody download() {
    return outputStream -> {
        try (InputStream input = fileService.openInputStream()) {
            input.transferTo(outputStream);
        }
    };
}
```

Đây là **snippet**: `fileService` chưa khai báo, controller/response headers chưa hoàn chỉnh và cần import `StreamingResponseBody`, `InputStream`. Nó cho phép ghi response **từ task executor sau khi initial Servlet thread được trả lại**. Nhưng `InputStream.transferTo(OutputStream)` dùng vòng đọc/ghi thường **blocking**; nếu client chậm, worker có thể đứng chờ output. Spring MVC khuyến nghị cấu hình async executor phù hợp khi dùng streaming.

### ResponseBodyEmitter và SSE

`ResponseBodyEmitter` có thể gửi nhiều object với `send(...)`/`complete()`. `SseEmitter` hỗ trợ SSE events. Mỗi request có thể tồn tại lâu mà không giữ initial Servlet thread, nhưng:

- Mỗi client vẫn chiếm connection, memory/state và có thể sử dụng worker khi gửi.
- Có thể xảy ra blocking writes hoặc queue tích tụ nếu client chậm.
- SSE thường đi một chiều server → client; muốn hai chiều, cân nhắc WebSocket.
- Đặt timeouts, heartbeat, limits, cleanup và client reconnect policy.
- Nếu đăng ký subscription từ broker, hủy khi emitter complete/error/timeout.

**Backpressure:** Servlet MVC emitters không tự tạo một giải pháp backpressure end-to-end giữa broker, application queue và browser. Nếu producer nhanh hơn consumer, cần buffer bounds, drop policy, producer pacing hoặc protocol phù hợp; đừng cứ gửi vô hạn vì initial thread đã rời request.

## 12. ThreadLocal, SecurityContext, MDC và transaction trong async

Một trong những lỗi khó phát hiện là suy ra "vẫn cùng HTTP request" nên mọi context của thread ban đầu vẫn tồn tại ở worker.

### 12.1. MDC/trace

MDC của logging thường dùng `ThreadLocal`. `Callable` chạy trên `mvc-work-*`, không nhất thiết mang `traceId`/`tenantId` mà Servlet filter gắn cho initial container thread. Nếu không có context propagation, logs từ producer mất correlation hoặc ghi nhầm giá trị tồn dư của task trước.

Một `TaskDecorator` có thể capture/apply MDC khi submit task, nhưng phải **restore/clear** trong finally. Khi kết hợp tracing/OpenTelemetry, dùng integration/Context propagation chính thức thay vì tự copy bừa mọi ThreadLocal.

### 12.2. SecurityContext

Spring Security cung cấp cơ chế integration cho Servlet async trong một số đường `Callable`, nhưng **không được giả định mọi executor/CompletableFuture/DeferredResult callback tự kế thừa principal**. Với producer executor tùy biến, cân nhắc `DelegatingSecurityContextAsyncTaskExecutor` hoặc explicit immutable user context; truyền ít dữ liệu cần thiết.

Đừng lưu nguyên request hoặc mutable security context trong long-lived queue rồi xử lý sau khi session đã hết hạn mà không xác minh policy. Phân quyền phải đặt tại endpoint và downstream service phù hợp.

### 12.3. Transaction

`@Transactional` thường gắn transaction với thread đang chạy method. Transaction trên controller initial thread **không tự tiếp tục** trong callable worker, deferred producer hoặc asynchronous dispatch. Nếu cần một DB transaction cho work, mở transaction **bên trong service method** được gọi trên worker. Không cố kéo dài một JDBC transaction suốt thời gian chờ event vài phút.

### 12.4. Locale và request-scoped data

`LocaleContextHolder`/`RequestContextHolder` có lifecycle riêng; Spring có một số integration cho Callable nhưng không bảo đảm mọi callback của riêng app nhận request context. Khi async producer cần locale, timezone hoặc tenant, nên truyền các giá trị **explicit** (bất biến) vào job/callback. Đừng giả định request-scoped bean còn hợp lệ sau khi request đã complete.

## 13. Throughput, thread pool và hiệu năng thực sự

### 13.1. Giải phóng Servlet thread có thể giúp điều gì?

Nếu 200 request đồng thời đang chờ remote events, `DeferredResult` cho phép initial Servlet threads trở về pool sớm, để container nhận các requests khác. Nhưng đồng thời vẫn có:

- 200 pending HTTP responses/connections.
- 200 async state objects.
- Timeout registrations, callbacks và possible buffered data.
- Event producer/subscriptions hoặc background tasks.
- Một Servlet thread ngắn khi result ready để redispatch và serialize response.

Nếu dùng `Callable` với blocking work, 200 requests có thể tràn một worker pool 8 threads + queue 32; 160 requests còn lại có thể bị reject/delay. Đó là **backpressure/overload cần thiết**, không phải lỗi phải “sửa” bằng cách spawn 200 unbounded threads.

### 13.2. Little's Law và giới hạn chờ

Một trực giác hiệu năng: số request đang chờ xấp xỉ `arrival rate × average time in system` khi đo trên một hệ thống tương đối ổn định. Nếu 100 request/giây mất 2 giây, có thể có khoảng 200 requests in flight; async không làm mất 200 pending connections, nó chỉ thay cách giữ threads.

Khi vẽ capacity plan, đo:
- Active/queued/rejected tasks ở executor.
- Current async requests, completion/timeout/cancel.
- Container threads busy và idle.
- HTTP client connection pool limits, DB pool saturation.
- CPU/GC, heap bytes cho response buffers và upload/download state.
- p50/p95/p99 latency và error rates.
- Client disconnects và ingress/reverse proxy timeouts.

Không nói "async luôn nhanh hơn sync". Với tác vụ CPU-bound rất ngắn, chuyển executor + redispatch có overhead và có thể chậm hơn. Với blocking operations, giải phóng Servlet threads có lợi cho isolation/availability nhưng không làm tổng wait-time thấp đi nếu downstream vẫn chậm.

### 13.3. Request deadline và circuit breaker

Khi gọi downstream chậm:
1. Đặt connection/read/request timeout của HTTP client/DB.
2. Giới hạn concurrent calls và queue.
3. Dùng cancellation/deadline propagation khi supported.
4. Fallback/circuit breaker/rate limit theo yêu cầu nghiệp vụ.
5. Không retry vô hạn trong worker; retry storms có thể làm downstream càng nghẽn.
6. Trả HTTP status đúng (`503` khi tạm quá tải, `504` ở gateway nếu phù hợp) với correlation ID và log an toàn.

Timeout chỉ ở Servlet MVC mà không đặt timeout cho client/DB là **thiết kế không đầy đủ**.

## 14. Spring MVC async so với Spring WebFlux

| Khía cạnh | Spring MVC Servlet async | Spring WebFlux |
| --- | --- | --- |
| Abstraction chính | MVC controllers, Servlet request/response | Reactive streams/publishers và reactive HTTP processing |
| Giải phóng initial thread | Có với Callable/DeferredResult/etc. | Reactive event-driven request lifecycle |
| Return types | Callable, DeferredResult, WebAsyncTask, CompletionStage, emitters | Mono, Flux và reactive types |
| I/O server | Servlet container, có Servlet 3.1 non-blocking APIs nhưng MVC response write thường blocking | Designed cho non-blocking streaming I/O qua supported runtime/adapters |
| JDBC/JPA blocking | Vẫn blocking nếu dùng | Vẫn blocking nếu gọi từ event loop; phải offload hoặc đổi driver |
| Backpressure | Cần thiết kế riêng cho emitters/producer queues | Reactive Streams hỗ trợ demand/signals, nhưng phải xem từng boundary |
| Testing | MockMvc + asyncDispatch | WebTestClient + reactive test utilities |
| Migration | Thêm async trên MVC hiện có | Thay programming model/stack và có thể client/driver |
| Phù hợp | Tận dụng Spring MVC, blocking libraries, traffic cần tách Servlet threads | End-to-end async pipelines, streaming/large concurrency với non-blocking dependencies |

Không có một lựa chọn thắng mọi trường hợp. Với MVC đang dùng Hibernate ORM/JPA/JDBC blocking, `Callable` hoặc `DeferredResult` + bounded worker có thể là giải pháp incremental. Nếu bottleneck chính là số lượng kết nối đồng thời và toàn bộ data path có non-blocking network/DB clients, WebFlux có thể giảm thread consumption. Nhưng nếu đưa `block()`/JDBC blocking vào event loop, lợi ích sẽ mất và throughput có thể tệ.

**WebFlux không đồng nghĩa với Netty trong mọi deployment**; nó có thể chạy trên runtime adapters khác. Phân biệt **programming model** (reactive), **server runtime** (Servlet/Netty) và **các thư viện I/O thực tế**.

## 15. Các lỗi phổ biến khi áp dụng Servlet async

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `IllegalStateException` báo async unsupported | Servlet/filter chain không `asyncSupported` hoặc dispatcher mapping thiếu | Kiểm tra đăng ký Servlet/filters và ASYNC dispatch |
| Dùng Callable mà threads vẫn cạn | Blocking work chuyển từ container sang worker pool | Bound executor, downstream timeout, đo worker utilization |
| DeferredResult bị timeout dù producer xong | Race, queue quá dài, result set sau timeout | Kiểm tra `setResult` boolean, queue latency và deadline |
| HTTP response kết thúc nhưng task vẫn chạy | MVC timeout không tự cancel downstream work | Truyền cancellation/deadline, cleanup producer/connection |
| `AsyncTaskExecutor` default không chịu tải | Không cấu hình pool/queue phù hợp | `WebMvcConfigurer.configureAsyncSupport` với bounded executor |
| Request không async dù có `@Async` method | `@Async` chỉ đổi nơi gọi method, controller return value không async | Trả Callable/DeferredResult/CompletionStage phù hợp |
| MDC/traceId biến mất ở worker | ThreadLocal không tự propagate | TaskDecorator/Context propagation, clear finally |
| SecurityContext không có trong producer | Tự dùng executor bên ngoài security integration | Explicit context hoặc delegating executor, xác minh ACL |
| Lazy-loading/transaction exception | Transaction chỉ mở ở initial thread | Service transaction bên trong worker, DTO boundaries |
| `StreamingResponseBody` chậm với slow client | `OutputStream.write` blocking trong worker | Pool thích hợp, flow control, native nonblocking APIs nếu cần |
| SSE làm memory tăng dần | Emitter/subscription không cleanup, client chậm | Bounds, callbacks, heartbeat, cancellation |
| MockMvc test fail vì response chưa có | Chưa gọi `asyncDispatch` | `request().asyncStarted()` rồi `asyncDispatch(result)` |
| Controller được gọi "hai lần" trong logs | Confuse ASYNC redispatch/filters/interceptors với controller return value | Log DispatcherType, lifecycle; không duplicate business action |
| Timeout ở proxy trước Spring MVC | Ingress idle timeout thấp hơn MVC timeout | Align end-to-end timeouts, keepalive theo policy |
| CPU tăng sau khi đổi async | Executor dispatch overhead, oversubscription, retry storms | Benchmark tải thật, tune bounded concurrency |
| Non-blocking WriteListener luôn quay vòng | Không thoát khi `isReady()==false` | Chỉ write lúc ready; chờ callback kế tiếp |
| Cố đọc file/DB đồng bộ trên event loop | Blocking I/O vẫn block thread phản ứng | Dùng non-blocking driver hoặc offload bounded scheduler |

Checklist debug cụ thể:

1. Quan sát `DispatcherType.REQUEST` và `DispatcherType.ASYNC` cùng correlation ID.
2. Kiểm tra Controller return type; đang dùng Callable/DeferredResult hay sync DTO?
3. Xem cấu hình `asyncSupported`/ASYNC dispatcher mappings cho Servlet và filters.
4. Đo thread names của producer/worker và container, không chỉ đo total thread count.
5. Đo thời gian chờ downstream, MVC timeout, proxy timeout và queue wait riêng.
6. Nếu có `DeferredResult`, kiểm tra hoàn thành bằng `setResult` hay error/timeout, cleanup listeners.
7. Với streaming, đo time spent trong `write` và tốc độ consumer.
8. Kiểm tra MDC/SecurityContext/LocaleContext/transaction boundaries trên từng executor.
9. Dùng MockMvc `asyncDispatch`, rồi bổ sung live HTTP server test khi cần verify disconnect/network/proxy.
10. Nếu mục tiêu là non-blocking end-to-end, kiểm tra **từng API I/O** (HTTP, DB, filesystem, response write) chứ không chỉ kiểu trả về.

## 16. Chọn kỹ thuật theo loại công việc

| Tình huống | Hướng phù hợp |
| --- | --- |
| Controller gọi DB JDBC blocking lâu nhưng muốn bảo vệ Servlet thread pool | Callable/WebAsyncTask + bounded executor, DB timeout |
| Phải chờ event/message broker callback mà không có thread riêng đứng đợi | DeferredResult + event subscription/callback và cleanup |
| HTTP client trả CompletableFuture từ I/O async thật sự | Controller return CompletableFuture/CompletionStage hoặc adapt qua DeferredResult |
| Tạo báo cáo CPU-bound 20 ms | Thường sync hoặc xử lý worker phù hợp theo benchmark; async không tự nhanh hơn |
| Tạo báo cáo lâu nhiều phút | Job queue + `202 Accepted` + polling/webhook, không giữ HTTP connection vô hạn |
| Trả tệp lớn qua StreamingResponseBody | MVC async executor và kiểm soát blocking writes |
| SSE hàng nghìn clients cập nhật liên tục | Cân nhắc WebFlux/non-blocking pipelines, bounds và heartbeat |
| Cần non-blocking Servlet stream ở mức thấp | Servlet 3.1 `ReadListener`/`WriteListener` với readiness contract |
| End-to-end network + data-store reactive | WebFlux và non-blocking clients/drivers, tránh blocking trên event loop |
| Cần hỗ trợ existing Servlet filters, JSP, blocking Spring MVC ecosystem | Tiếp tục MVC, chỉ dùng async tại nơi thực sự có lợi |

Một endpoint thời gian chờ quá dài có thể nên **không** giữ HTTP connection. Với tác vụ báo cáo mất nhiều phút, API `POST /reports` trả `202 Accepted` cùng job ID, client `GET /reports/{id}/status` hoặc nhận webhook là một lựa chọn giúp xử lý retries, scaling và timeouts ổn định hơn. Servlet async phù hợp các request chờ không quá lâu và có policy rõ, không thay message queue/job orchestration.

## 17. Bài tập tự kiểm tra

1. Vì sao `Callable` có thể giải phóng Servlet request thread nhưng vẫn **block** một worker thread?
2. `DeferredResult` có tự sinh thread và tự gọi I/O không?
3. Trong MVC async lifecycle, request hoàn thành ở initial `REQUEST` dispatch hay có một `ASYNC` redispatch?
4. `request.startAsync()` (Servlet 3.0) và `ServletOutputStream.setWriteListener()` (Servlet 3.1) khác trách nhiệm nào?
5. Đặt `MVC timeout=3s` có tự dừng một JDBC query 60s không?
6. `StreamingResponseBody` có bảo đảm socket write không bao giờ block thread không?
7. Vì sao Spring MVC cần cấu hình `AsyncTaskExecutor` thay vì unbounded threads cho Callable?
8. Nếu response tới user đã timeout, `DeferredResult.setResult(value)` gọi muộn có thể xảy ra chuyện gì?
9. Test MockMvc cho Callable phải có những bước nào?
10. `@Async` annotation trên service có tự khiến HTTP response non-blocking không?
11. Vì sao `ThreadLocal` transaction/MDC/SecurityContext không thể mặc định được giữ qua worker executor?
12. Nếu đổi sang WebFlux mà vẫn gọi JDBC blocking trực tiếp trên event loop, có đạt end-to-end non-blocking không?
13. Khi nào nên dùng `DeferredResult` thay Callable?
14. Async có làm mất chi phí socket/buffer của mỗi pending HTTP response không?
15. Với SSE client chậm, vì sao vẫn phải cần backpressure/buffer limits dù request thread đã được giải phóng?

**Gợi ý:** (1) Callable chạy trên executor, blocking call chặn executor thread. (2) Không; producer/event thread do ứng dụng quyết định. (3) MVC tiếp tục bằng ASYNC dispatch. (4) Lifecycle giải phóng/tiếp tục request so với I/O readiness. (5) Không; cần cancellation/downstream timeout. (6) Không; OutputStream.write có thể block. (7) Bảo vệ concurrency/queue/memory. (8) Result có thể bị từ chối vì đã complete. (9) Request asyncStarted → MvcResult → asyncDispatch → assert. (10) Không; method execution và MVC return-type handling là hai lớp khác. (11) Thread-bound context. (12) Không. (13) Khi kết quả đến từ callback/event không cần worker đứng chờ. (14) Không. (15) Producer có thể nhanh hơn tốc độ network/consumer.

## 18. Tài liệu tham khảo chính thức

- [Spring Framework — Asynchronous Requests in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework 6.1 — AsyncSupportConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/config/annotation/AsyncSupportConfigurer.html)
- [Spring Framework 6.1 — DeferredResult Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/context/request/async/DeferredResult.html)
- [Spring Framework 6.1 — WebAsyncTask Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/context/request/async/WebAsyncTask.html)
- [Spring Framework — MVC Streaming](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html#webmvc-ann-async-http-streaming)
- [Spring Framework — MVC Compared to WebFlux](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html#webmvc-ann-async-vs-webflux)
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Jakarta Servlet 6.0 — AsyncContext](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/asynccontext)
- [Jakarta Servlet 6.0 — ReadListener](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/readlistener)
- [Jakarta Servlet 6.0 — WriteListener](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/writelistener)
- [Spring MVC Testing — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework/async-requests.html)

**Tổng kết:** Servlet async giải phóng **initial Servlet request thread** khi HTTP response còn pending và dùng **ASYNC dispatch** để hoàn tất sau. `Callable` thường chuyển blocking work sang executor; `DeferredResult` có thể chờ một external callback mà không cần thread đứng đợi riêng; `WebAsyncTask` thêm timeout/callbacks. Đây không phải bằng chứng I/O non-blocking. **Servlet 3.1 ReadListener/WriteListener** giải quyết socket readiness ở tầng thấp, còn WebFlux cung cấp mô hình reactive hơn khi các dependencies hỗ trợ non-blocking end-to-end. Khi triển khai, hãy đo thread/queue/downstream timeout, đảm bảo security/trace context, cleanup và giới hạn tải — không chỉ đổi return type rồi coi ứng dụng đã "non-blocking".
