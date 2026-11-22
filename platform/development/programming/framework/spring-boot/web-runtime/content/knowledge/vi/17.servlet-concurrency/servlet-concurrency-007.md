# Thời gian chờ async, hủy tác vụ và xử lý máy khách ngắt kết nối trong Servlet/Spring MVC

Trong **Servlet stack**, một HTTP request có thể khởi chạy công việc tốn thời gian rồi trả kết quả bất đồng bộ (async). Khi đó, luồng tiếp nhận request có thể được trả lại cho Servlet container trong lúc response vẫn còn mở. Tuy nhiên, **request hết thời gian chờ**, **công việc nền bị hủy** và **client đóng kết nối** là ba sự kiện khác nhau. Nhầm lẫn giữa chúng sẽ gây rò rỉ tác vụ, giữ tài nguyên quá lâu, ghi dữ liệu sau khi response đã hoàn tất hoặc trả mã HTTP không đúng.

Bài này giải thích vòng đời Servlet async, cách thiết lập timeout và cleanup trong Spring MVC, giới hạn của việc hủy bằng `Future.cancel(true)`, cũng như phương án ứng xử khi máy khách ngắt kết nối. Các ví dụ dành cho **Java 17+**, **Spring Boot 3.x**, **Spring MVC trên Servlet container**; không giả định rằng Spring MVC có cơ chế hủy tự động như một luồng reactive.

## 1. Async trong Servlet hoạt động như thế nào?

### 1.1. Request đồng bộ và bất đồng bộ

**Đồng bộ:** luồng Servlet nhận request → gọi xử lý (có thể chặn I/O hoặc ngủ) → ghi response → hoàn tất; luồng đó bị chiếm suốt thời gian xử lý.

**Servlet async:** luồng Servlet nhận request → bật async và trả khỏi filter/servlet chain → container giữ request/response ở trạng thái async nhưng trả luồng tiếp nhận về pool → công việc chạy trên executor hoặc kết quả đến từ hệ thống khác → Servlet container thực hiện một lần **ASYNC dispatch** để Spring MVC hoàn thiện response.

Với Servlet API thấp hơn, có `request.startAsync()` để lấy `AsyncContext`, sau đó có thể `dispatch()` hoặc `complete()`. Servlet/filter cần hỗ trợ async (cấu hình `asyncSupported` và dispatcher type phù hợp). Spring MVC thường quản lý cơ chế này thay bạn khi controller trả về:

- `Callable<T>`: Spring MVC gửi công việc vào `AsyncTaskExecutor`. Có thể dùng `WebAsyncTask<T>` để chọn timeout/executor và đăng ký callback.
- `DeferredResult<T>`: controller trả một “ô chứa kết quả”; một tác nhân bên ngoài gọi `setResult` hoặc `setErrorResult` sau đó.
- `ResponseBodyEmitter`, `SseEmitter`, `StreamingResponseBody`: phục vụ stream và dữ liệu đẩy nhiều lần; việc ghi network có quy tắc khác với một giá trị đơn lẻ.

**Async không đồng nghĩa non-blocking trên mọi luồng.** Nếu bên trong `Callable`/worker vẫn gọi JDBC hoặc `Thread.sleep`, luồng worker vẫn có thể bị chặn. Lợi ích trực tiếp là luồng nhận request được trả về container sớm, không phải có thêm tài nguyên vô hạn.

### 1.2. Các trạng thái cần phân biệt

```text
HTTP request đến
      |
      v
Controller trả DeferredResult / Callable
      |
      v
Servlet async bắt đầu; luồng request ban đầu được giải phóng
      |
      +---- worker hoàn tất ------> setResult / setErrorResult
      |                                    |
      |                                    v
      |                               ASYNC dispatch -> response -> complete
      |
      +---- async timeout ----------> onTimeout -> thử đặt response lỗi
      |                                    |
      |                                    +-> yêu cầu dừng worker -> complete
      |
      +---- lỗi được container thấy -> onError / xử lý lỗi -> complete
      |
      +---- client đóng socket ------> có thể CHƯA được phát hiện ngay
                                           |
                                  lỗi ở lần ghi/flush sau hoặc timeout
```

Khi container đã hoàn tất async request, không còn một response hợp lệ để ứng dụng “ghi thêm”. Một task vẫn chạy sau đó có thể xử lý công việc nội bộ, nhưng không thể tin rằng kết quả muộn của nó còn được gửi cho client.

## 2. Timeout: có nhiều đồng hồ, không chỉ một

| Loại thời gian chờ | Ai kiểm soát | Hậu quả quan trọng |
| --- | --- | --- |
| **Client timeout** | Trình duyệt, `curl`, SDK, ứng dụng di động | Client có thể bỏ chờ và đóng kết nối; server có thể vẫn đang chạy. |
| **Gateway/proxy/load balancer timeout** | Reverse proxy/API gateway | Proxy có thể đóng kết nối hoặc trả `504 Gateway Timeout` khi chờ upstream quá lâu; ứng dụng backend chưa chắc biết ngay. |
| **Servlet async timeout** | Servlet container/Spring MVC | Request đang ở chế độ async bị timeout; callback/interceptor được kích hoạt. Không tự động đảm bảo worker dừng. |
| **Task/dependency deadline** | Mã ứng dụng, HTTP client gọi downstream, JDBC driver, queue client | Giới hạn công việc thực sự được phép tiêu tốn thời gian; cần cấu hình riêng với HTTP response timeout. |

Ví dụ: client chỉ chờ **2 giây**, gateway chờ **4 giây**, Spring MVC async timeout **5 giây**, còn truy vấn database có timeout **30 giây**. Client có thể đã bỏ chờ ở giây thứ 2, trong khi backend vẫn giữ worker và kết nối database. Vì thế phải **thiết kế deadline end-to-end**, với giới hạn ở các phụ thuộc và cơ chế hủy thực thi phù hợp.

### 2.1. Cấu hình timeout ở Spring Boot/MVC

Trong `application.yml`:

```yaml
spring:
  mvc:
    async:
      request-timeout: 5s
```

`spring.mvc.async.request-timeout` là thời gian chờ mặc định cho **request xử lý async của Spring MVC**. Nếu không cấu hình, giá trị thực tế phụ thuộc Servlet container. Đơn vị `5s` dùng cú pháp `Duration` của Spring Boot; cũng có thể chọn giá trị theo đơn vị mà cấu hình hỗ trợ. Không coi cấu hình này là timeout áp dụng cho mọi request đồng bộ, truy vấn JDBC, lời gọi HTTP outbound hoặc tác vụ trong queue.

Có thể ghi đè theo từng request:

```java
// Đoạn minh họa bên trong controller Spring MVC.
DeferredResult<String> deferred = new DeferredResult<>(2_000L); // 2 giây
// ... trả deferred và đặt kết quả từ một tác nhân khác
```

Với `Callable<T>`, có thể dùng `WebAsyncTask<T>` để chỉ định timeout và callback:

```java
// Đoạn minh họa; "service" là một service do ứng dụng cung cấp.
WebAsyncTask<String> response = new WebAsyncTask<>(2_000L, () -> service.load());
response.onTimeout(() -> "fallback on timeout");
response.onCompletion(() -> service.cleanup());
return response;
```

Đoạn `WebAsyncTask` trên minh họa API chứ không phải một class độc lập; cần controller, khai báo kiểu trả về phù hợp và service thực tế. Trong production, **không** dùng một chuỗi fallback thành công như ví dụ nếu việc hết giờ cần trả mã lỗi: dùng `ResponseEntity` hay xử lý ngoại lệ để phản ánh thất bại.

Nếu tự quản lý Servlet bằng `AsyncContext`, có `setTimeout(long milliseconds)` và `AsyncListener.onTimeout(...)`; trách nhiệm `dispatch()`/`complete()`, xử lý lỗi và quyền ghi response thuộc mã của bạn. Khi đã dùng Spring MVC `DeferredResult`, tránh gọi xen kẽ các hàm lifecycle thấp cấp gây double-completion.

### 2.2. HTTP status khi timeout

- Spring MVC có thể xử lý timeout mặc định thông qua `AsyncRequestTimeoutException` và trả một lỗi server (thường `503 Service Unavailable` tùy cấu hình/handler). Bạn có thể chủ động trả status và body dễ hiểu bằng `onTimeout`.
- `503` hợp lý khi server tạm thời không thể hoàn tất request. `504 Gateway Timeout` thường do **gateway/proxy** phát ra khi upstream chậm; đừng dùng `504` cho mọi tác vụ nội bộ quá hạn chỉ vì tên gọi nghe giống “timeout”.
- `408 Request Timeout` liên quan việc server không nhận trọn request từ client trong thời gian chờ, **khác** việc server xử lý một async request quá lâu.
- Nếu client đã đóng kết nối, server có thể **không gửi được bất kỳ status nào** nữa. Không giả định sẽ luôn có một response JSON lỗi khi timeout xảy ra.

## 3. Hủy tác vụ: timeout không phải nút “kill”

Một request mất hiệu lực **không** đồng nghĩa task đã dừng. Có ba lớp trạng thái riêng biệt:

1. **Response/request lifecycle:** còn có thể trả kết quả HTTP hay đã timeout/completed?
2. **Công việc trên executor:** còn chạy, đã xong, đã nhận tín hiệu hủy hay đang mắc kẹt ở tác vụ không hỗ trợ ngắt?
3. **Hiệu ứng bên ngoài:** đã gửi email, ghi database, publish message, gọi hệ thống thứ ba hoặc commit transaction chưa?

Ví dụ, khi request tìm kiếm bị timeout, bạn có thể muốn hủy truy vấn; nhưng nếu đó là request **tạo đơn đã commit**, hủy thread không làm rollback một giao dịch đã hoàn tất. Không được suy luận “client đã ngắt → nghiệp vụ chắc chắn chưa thực hiện”.

### 3.1. `Future.cancel(true)` thực sự làm gì?

Với task nộp qua `ExecutorService.submit(...)`, `Future.cancel(true)` đánh dấu nỗ lực hủy và có thể **interrupt** luồng đang chạy. Java không có cơ chế an toàn để cưỡng bức chấm dứt mọi mã đang chạy:

- `Thread.sleep`, `BlockingQueue.take`, `CountDownLatch.await` và nhiều API chặn có thể ném `InterruptedException`. Task nên kết thúc gọn, khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` khi bắt exception.
- Vòng lặp CPU nên tự kiểm tra `Thread.currentThread().isInterrupted()` và thoát khi được yêu cầu.
- I/O, JDBC, native calls, RPC và SDK ngoài có thể bỏ qua hoặc trì hoãn interrupt. Cần thêm timeout riêng ở tầng thư viện/phụ thuộc; đôi khi phải dùng API cancel riêng.
- Giá trị `true` từ `cancel(true)` hay `isCancelled()` **không chứng minh** tất cả side effects đã dừng. Nó diễn đạt trạng thái của `Future`.
- `CompletableFuture.cancel(true)` cũng **không** bảo đảm ngắt luồng đang chạy theo cách `FutureTask` của `ExecutorService` có thể làm. Đừng chuyển code từ `Future` sang `CompletableFuture` rồi mặc định tin worker được interrupt.

Chương trình Java 17 độc lập sau đây chứng minh cách yêu cầu hủy một tác vụ đang chờ:

File `CancellationDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        try {
            Future<?> job = executor.submit(() -> {
                started.countDown();
                try {
                    neverReleased.await();
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            System.out.println("cancel requested = " + job.cancel(true));
            System.out.println("future cancelled = " + job.isCancelled());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac CancellationDemo.java
java CancellationDemo
```

Stdout (vì `neverReleased` không bao giờ được nhả và `started.await()` đảm bảo task đã chạy):

```text
cancel requested = true
future cancelled = true
```

Ví dụ cho thấy tín hiệu hủy được chấp nhận; ở task thật vẫn phải kiểm tra mã xử lý có chủ động thoát khi bị interrupt và có bỏ dở tài nguyên đúng cách hay không.

### 3.2. Thiết kế cleanup idempotent

Một request có thể gần như đồng thời nhận **kết quả**, **timeout** và **lỗi network**. Vì thế:

- Dùng một điểm quyết định kết quả response (`DeferredResult.setResult`/`setErrorResult` trả boolean cho biết kết quả có được nhận hay không). Không ghi HTTP response hai lần.
- Dùng `onCompletion` cho thao tác dọn dẹp cuối cùng có thể gọi lặp an toàn, ví dụ hủy task chưa xong, đóng subscription, xóa entry khỏi map. Callback này có thể xảy ra do thành công, timeout hoặc lỗi; bản thân nó **không kết luận** client đã disconnect.
- Dùng `onTimeout` để quyết định fallback/status và yêu cầu hủy công việc không còn cần thiết.
- Dùng `onError` để ghi nhận lỗi có bằng chứng và yêu cầu hủy; một lỗi async có thể do nhiều nguyên nhân, không được tự động gắn nhãn “client bỏ đi”.
- Không nuốt hết `InterruptedException` rồi tiếp tục như không có gì. Không giữ mã tham chiếu của `HttpServletResponse` để worker cố ghi body sau khi async complete.

## 4. Ví dụ Spring Boot 3.x: timeout, hủy Future và cleanup

Ví dụ gồm **hai file Java đầy đủ** trong một dự án Spring Boot Java 17 có dependency `spring-boot-starter-web`. Dùng pool riêng để minh họa worker; cơ chế cancel chỉ là best-effort. Trong production, nên cấu hình **executor có giới hạn pool + queue, chính sách từ chối, quan sát tải** thay vì `Executors.newFixedThreadPool` (có hàng đợi không giới hạn).

File `src/main/java/demo/async/AsyncDemoApplication.java`:

```java
package demo.async;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncDemoApplication.class, args);
    }
}
```

File `src/main/java/demo/async/AsyncWorkController.java`:

```java
package demo.async;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import jakarta.annotation.PreDestroy;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/demo")
public class AsyncWorkController {
    private final ExecutorService workers = Executors.newFixedThreadPool(4);

    public record Payload(String state, String detail) {}

    @GetMapping("/job")
    public DeferredResult<ResponseEntity<Payload>> job(
            @RequestParam(defaultValue = "30") int units) {

        if (units < 0 || units > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "units must be between 0 and 100");
        }

        // Giới hạn vòng đời HTTP async của endpoint này là 1,5 giây.
        DeferredResult<ResponseEntity<Payload>> deferred =
                new DeferredResult<>(1_500L);

        Future<?> running = workers.submit(() -> {
            try {
                // Giả lập 100 ms/công đoạn; InterruptedException giúp thoát.
                for (int i = 0; i < units; i++) {
                    Thread.sleep(100L);
                }
                deferred.setResult(ResponseEntity.ok(
                        new Payload("completed", "units=" + units)));
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } catch (RuntimeException failure) {
                deferred.setErrorResult(failure);
            }
        });

        deferred.onTimeout(() -> {
            // Nếu kết quả chưa được quyết định, trả phản hồi timeout.
            deferred.setErrorResult(
                    ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                            .body(new Payload(
                                    "timed_out", "async request exceeded 1500 ms")));
            // Đề nghị dừng task; mã worker phải hợp tác với interrupt.
            running.cancel(true);
        });

        // Có lỗi async do container ghi nhận: yêu cầu dừng work.
        deferred.onError(error -> running.cancel(true));

        // Cleanup cuối đời request: an toàn dù task đã xong.
        deferred.onCompletion(() -> running.cancel(true));

        return deferred;
    }

    @PreDestroy
    public void shutdownWorkerPool() {
        workers.shutdownNow();
    }
}
```

**Tại sao ví dụ này hợp lý?**

1. Controller trả `DeferredResult` nhanh, để Servlet container giữ response mở trong async mode. `workers.submit` chạy phần công việc giả lập trên pool riêng.
2. Với `units=2`, worker thường hoàn thành sau khoảng 200 ms, gọi `setResult` và client nhận `200 OK` cùng JSON `{"state":"completed","detail":"units=2"}`.
3. Với `units=30`, worker dự kiến cần khoảng 3 giây, vượt timeout async 1,5 giây. Callback `onTimeout` thử đặt `503 Service Unavailable` kèm JSON `{"state":"timed_out","detail":"async request exceeded 1500 ms"}`, sau đó gọi `running.cancel(true)`. Task đang ở `Thread.sleep` sẽ nhận interrupt và thoát.
4. Khi request kết thúc, `onCompletion` vẫn được gọi và việc hủy lặp trên một `Future` đã hoàn tất là vô hại; không suy luận callback này là thông báo client disconnect.
5. Nếu kết quả thắng cuộc đua với timeout, lệnh `setErrorResult` muộn có thể không được nhận và không nên thay đổi response đã quyết định. Trong production, kiểm tra boolean trả về từ `setResult/setErrorResult` khi cần metric về “late result” và quyết định cleanup thống nhất.

**Giới hạn của ví dụ:** Vì `Thread.sleep` dễ bị interrupt, phần task dừng tương đối nhanh. Một lời gọi JDBC hoặc REST sang hệ thống ngoài có thể không phản ứng tương tự; phải đặt timeout/cancel riêng cho dependency. Ví dụ không có auth, tracing, giới hạn hàng đợi, rate limiting hay lưu trữ lâu dài.

Thêm dependency vào dự án Boot Gradle hiện có, nếu chưa có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Chạy dự án với wrapper của nó: `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Sau khi ứng dụng khởi động, dùng lệnh sau (cú pháp Bash):

```bash
# Hoàn tất nhanh, dự kiến HTTP 200 và state=completed
curl -i 'http://localhost:8080/demo/job?units=2'

# Vượt timeout của Spring MVC, dự kiến HTTP 503 và state=timed_out
curl -i 'http://localhost:8080/demo/job?units=30'

# Input không hợp lệ, dự kiến HTTP 400
curl -i 'http://localhost:8080/demo/job?units=-1'

# Client chỉ chờ tối đa 0,2 giây rồi bỏ chờ
curl --max-time 0.2 -i 'http://localhost:8080/demo/job?units=30'
```

Các status trên là **kết quả kỳ vọng trong điều kiện thử bình thường**, không phải cam kết chính xác thời điểm callback vì còn scheduling và tải máy. Lệnh cuối có thể báo lỗi `curl: (28) Operation timed out` ở **client**, không chứng minh rằng Servlet đã nhận ngay thông báo disconnect hay worker dừng tức thì. Đây là hai sự kiện cần đo riêng.

### 4.1. Nếu dùng `Callable`, `WebAsyncTask` hoặc `DeferredResult` khác nhau ở đâu?

- `Callable`: phù hợp khi việc tính kết quả tự chạy trên executor của MVC; dễ dùng nhưng muốn hủy thực thi theo chính sách cụ thể phải quản lý executor/task/lifecycle cẩn thận.
- `WebAsyncTask`: bao `Callable` cùng timeout, executor và callback có sẵn; callback trả một fallback/giá trị response, nhưng **không mặc nhiên đảm bảo hủy việc đang chạy**.
- `DeferredResult`: phù hợp khi kết quả được đẩy vào từ một task, listener, message broker hay callback bên ngoài. Ứng dụng có thể giữ `Future` hoặc cancellation token và kết nối lifecycle của HTTP request với task.
- `SseEmitter`/streaming: tạo nhiều lần ghi; nếu client biến mất, lỗi ghi dữ liệu hoặc heartbeat thường giúp phát hiện, nhưng có thể không có tín hiệu tức thì.

Nếu chọn `Callable` hoặc streaming trong production, xem lại `WebMvcConfigurer.configureAsyncSupport` để dùng `AsyncTaskExecutor` phù hợp. Executor mặc định của MVC không nên được mặc định coi là thiết kế chịu tải ổn định; cần giới hạn và quan sát tài nguyên.

## 5. Máy khách ngắt kết nối: giới hạn lớn của Servlet

**Servlet API không cung cấp một sự kiện tiêu chuẩn bảo đảm thông báo tức thời rằng client đã ngắt socket.** Khi backend đang xử lý nhưng chưa ghi gì, việc người gọi đóng trình duyệt hay `curl` dừng không nhất thiết làm server nhận thông tin ngay. Không thể chỉ đăng ký callback để chắc chắn phát hiện trong vài mili giây.

Thực tế có thể xảy ra:

- Client đóng kết nối **trước khi response có dữ liệu**: server vẫn tính toán, sau đó mới thấy lỗi khi ghi/flush hoặc vẫn chỉ dừng do timeout.
- Client đóng kết nối **trong khi stream**: lần ghi tiếp theo có thể ném `IOException`, chẳng hạn broken pipe/reset by peer; thông điệp chính xác phụ thuộc container/OS/proxy.
- Client đóng kết nối **sau khi server đã commit side effect**: request không còn người đợi nhưng giao dịch có thể đã thành công; không có cơ chế “rollback vì HTTP disconnect” tự động.
- Proxy buffer hoặc connection bị giữ nửa mở: ứng dụng có thể quan sát sự kiện muộn, và không nên biến sự thiếu sự kiện thành bảo đảm client vẫn ở đó.

### 5.1. `onError` và `onCompletion` cho biết gì?

- `DeferredResult.onError(Consumer<Throwable>)` chạy khi async request gặp lỗi do container nhận biết. Có thể dọn dẹp hoặc đặt error result **nếu response còn khả dụng**; không phải callback disconnect độc lập hay bảo đảm lúc socket đóng.
- `DeferredResult.onCompletion(Runnable)` chạy khi lifecycle async hoàn tất vì **bất kỳ lý do nào**, kể cả thành công, timeout hay lỗi network. Dùng nó để cleanup, **không log mọi lần gọi là “client aborted”**.
- `onTimeout` chạy khi async timeout thực sự được container xử lý. Đừng xem nó là bằng chứng client đã bỏ đi.
- Trường hợp streaming, nếu `ResponseBodyEmitter.send(...)` ném `IOException` do remote disconnect, **để Servlet container/Spring MVC xử lý thông báo lỗi**; theo tài liệu Spring MVC, ứng dụng không nên gọi thêm `emitter.complete()` hoặc `emitter.completeWithError()` ngay trong nhánh `IOException` đó vì container sẽ khởi phát error notification và Spring xử lý lần dispatch cuối.

Không có HTTP status chuẩn nào tên **499** do RFC định nghĩa cho trường hợp này; `499 Client Closed Request` thường xuất hiện trong log của một số proxy như Nginx để mô tả client đóng kết nối. Không đặt `499` thành response chuẩn để mong gửi cho client đã đi mất.

### 5.2. Heartbeat cho SSE/long-lived streaming

Với kết nối `text/event-stream`, server có thể định kỳ gửi một SSE **comment heartbeat** (thí dụ dòng bắt đầu bằng dấu `:`) để thử ghi dữ liệu và nhận biết kết nối hỏng sớm hơn. Khi ghi thất bại, cleanup task/subscription liên quan; khi có `IOException` từ `SseEmitter.send`, để Spring/container xử lý lỗi async như ở trên.

Heartbeat không phải bảo đảm phát hiện tức thời: proxy có thể buffer, mạng có thể chậm và không phải mọi lần write đều lập tức thông báo socket chết. Chọn chu kỳ phù hợp với idle timeout của proxy, tải mạng và mục đích sản phẩm. Với giao thức cần tín hiệu sống hai chiều, WebSocket với heartbeat/ping hoặc một cơ chế messaging chuyên dụng có thể phù hợp hơn.

## 6. Quyết định có hủy nghiệp vụ khi HTTP request kết thúc

**Trường hợp A — request tính toán chỉ phục vụ người đang chờ:** ví dụ tìm kiếm tốn CPU, render tạm thời. Nếu timeout hoặc phát hiện disconnect, nên phát tín hiệu hủy, ngừng tải phụ thuộc khi có thể, giải phóng tài nguyên và chặn gửi kết quả muộn.

**Trường hợp B — request tạo công việc bền vững:** ví dụ tạo hóa đơn, gửi email theo hàng đợi, xuất báo cáo được người dùng khởi tạo. Nếu đã trả `202 Accepted` và có job ID, việc client đóng tab **không nên tự hủy job** trừ khi API quy định rõ. Cung cấp endpoint xem trạng thái/hủy riêng, có xác thực, ghi lại trạng thái task và xử lý yêu cầu hủy idempotent.

**Trường hợp C — thao tác có side effect không thể thu hồi:** hủy future sau khi database commit hoặc hệ thống thứ ba đã nhận lệnh không đồng nghĩa undo. Cần state machine nghiệp vụ, idempotency key, transaction/compensation khi cần, và khả năng tra cứu kết quả nếu client thử lại.

| Tình huống | Response nếu còn gửi được | Hành động backend |
| --- | --- | --- |
| Công việc hoàn tất trước deadline | `200`/`201` theo nghiệp vụ | Gửi kết quả, cleanup handle. |
| Async request hết giờ, công việc chỉ phục vụ response | Có thể `503`/response theo hợp đồng API | `onTimeout` yêu cầu hủy task, timeout downstream, cleanup. |
| Worker lỗi bất ngờ | `5xx` thích hợp nếu response chưa commit | Log nguyên nhân, tránh lộ thông tin, cleanup. |
| Client đã đóng connection | Có thể **không trả được status** | Phát hiện best-effort, dừng việc không cần thiết, không ghi body muộn. |
| Durable job đã tiếp nhận | `202` ở thời điểm tiếp nhận | Tiếp tục xử lý riêng; có status/cancel endpoint nếu cần. |

## 7. Kiểm thử và quan sát các tình huống khó

Đừng chỉ test happy path. Tối thiểu cần có:

1. **Fast completion:** task kết thúc trước timeout; body/status đúng; `onCompletion` chạy; future không còn chiếm worker.
2. **Async timeout:** task chạy lâu; status/body lỗi có tính nhất quán; callback hủy được gọi; số task đang chạy giảm khi task hỗ trợ interrupt.
3. **Race completion vs timeout:** chạy nhiều lần quanh ranh giới deadline; chỉ có **một** kết quả được chấp nhận, không ghi response kép và không rò rỉ task.
4. **Dependency không phản ứng interrupt:** giả lập thư viện blocking; chứng minh request timeout **không** có nghĩa tài nguyên được thu hồi; xác nhận timeout riêng và cơ chế hủy của dependency.
5. **Client abort:** dùng `curl --max-time` hoặc chủ động đóng TCP; quan sát lỗi/cleanup thật ở môi trường có Servlet container và proxy tương tự production. **Đừng yêu cầu callback disconnect phải xảy ra ngay** vì API không bảo đảm.
6. **Streaming disconnect:** gửi các heartbeat, ngắt client và kiểm tra task phát stream chấm dứt khi lỗi được phát hiện; không lặp `completeWithError` sau `IOException` từ send.
7. **Business side effects:** xác nhận request bị hủy không khiến lần thử lại tạo trùng đơn hay gửi lặp email.

Với Spring MVC `MockMvc`, kiểm thử kết quả async thường theo chu trình `request().asyncStarted()` rồi `asyncDispatch(mvcResult)` để xác minh response. Tuy nhiên **MockMvc không thay thế** test timeout/network disconnect trên Servlet container thật, vì sự kiện socket, container và proxy không được mô phỏng đầy đủ.

Các metric/log hữu ích: thời lượng HTTP, số async request đang mở, timeout count, executor `active/queue/rejected`, số lần yêu cầu cancel, task thực sự kết thúc sau cancel, lỗi ghi stream, dependency latency và số tác vụ còn chạy sau response complete. Dùng request/correlation ID xuyên qua worker thread khi cần, nhưng đừng đặt toàn bộ URL, client ID tùy ý hoặc exception text làm nhãn metric khiến cardinality bùng nổ.

## 8. Lỗi thường gặp và checklist

**Lỗi:**
- Cấu hình mỗi `spring.mvc.async.request-timeout` rồi tin JDBC/HTTP client/worker sẽ tự hết hạn: **sai** vì timeout các tầng độc lập.
- Dùng `Future.cancel(true)` như “kill process”: chỉ là tín hiệu hủy best-effort, có thể không chặn side effect đã xảy ra.
- Trong `onCompletion` luôn đánh dấu “client disconnected”: callback này cũng chạy khi thành công.
- Trả `200` sau async timeout hoặc cố trả `504` cho mọi lỗi tính toán chậm: status cần phản ánh nguyên nhân và tầng đang chịu trách nhiệm.
- Sau khi `DeferredResult` đã hoàn tất vẫn ghi trực tiếp `HttpServletResponse`: có thể hỏng response hoặc lỗi ghi.
- Sau `SseEmitter.send` ném `IOException` lại gọi thêm `completeWithError`: làm trùng đường xử lý lỗi mà Spring/container đã phụ trách.
- Dùng pool/queue không giới hạn cho mọi request async; thread tiếp nhận được trả về nhưng worker và bộ nhớ vẫn có thể cạn.
- Đồng nhất việc người dùng rời trang với yêu cầu hủy một durable job; có thể làm mất tác vụ quan trọng.

**Checklist thiết kế:**

- [ ] Phân biệt timeout của client, proxy, Servlet async và dependency; chọn deadline có chủ đích.
- [ ] Quyết định nghiệp vụ có thể hủy hay phải hoàn tất dù kết nối đã đóng.
- [ ] Dùng `onTimeout`, `onError`, `onCompletion` cho đúng mục đích, xử lý race theo hướng idempotent.
- [ ] Task hỗ trợ interrupt/cancellation token; dependency có timeout và cleanup riêng.
- [ ] Không ghi response sau khi hoàn tất hoặc sau khi connection đã lỗi; trả HTTP status/body nhất quán khi còn có thể.
- [ ] Giới hạn executor pool/queue; có metric cho task tồn đọng, bị từ chối hoặc còn chạy sau timeout.
- [ ] Có integration test với server thật cho client abort, proxy timeout và stream heartbeat.

**Kết luận:** Servlet async giúp trả luồng xử lý HTTP về container nhưng không làm cho công việc nền tự biến mất. **Timeout kết thúc quyền chờ của request; cancellation là yêu cầu hủy công việc; disconnect là trạng thái network có thể được phát hiện muộn.** Thiết kế đúng cần phối hợp ba lifecycle này với timeout ở downstream, cleanup idempotent và contract nghiệp vụ.

### Tài liệu tham khảo

- Spring Framework — [Asynchronous Requests in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): `DeferredResult`, `Callable`, `WebAsyncTask`, xử lý lỗi, disconnect và cấu hình.
- Spring Framework — [DeferredResult Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/context/request/async/DeferredResult.html): hợp đồng `onTimeout`, `onError`, `onCompletion` và `setResult`.
- Spring Boot — [Common Application Properties](https://docs.spring.io/spring-boot/reference/appendix/application-properties/index.html): `spring.mvc.async.request-timeout`.
- Spring Framework — [MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): kiểm thử `asyncStarted`/`asyncDispatch`.
