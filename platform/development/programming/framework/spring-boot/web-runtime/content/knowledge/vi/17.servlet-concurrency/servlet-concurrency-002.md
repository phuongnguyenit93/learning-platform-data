# Servlet async và phân biệt với mã không chặn luồng

Trong Spring Boot sử dụng Spring MVC, một HTTP request đồng bộ thường giữ servlet container thread cho đến khi controller hoàn tất. **Servlet async** cho phép request tạm rời thread ban đầu nhưng vẫn giữ HTTP response đang chờ kết quả. Khi kết quả xuất hiện, container sẽ thực hiện xử lý tiếp hoặc async dispatch để trả response. **Điều này không làm JDBC, `Thread.sleep` hoặc HTTP client đồng bộ trở thành non-blocking**: nếu được đưa sang executor, công việc vẫn có thể chặn một worker khác.

Bài thuộc mục **Đồng thời Servlet**, áp dụng **Java 17+, Spring Boot 3.3.x, Spring MVC trên Jakarta Servlet**. Chúng ta sẽ phân biệt vòng đời request, async execution, non-blocking I/O; dùng `AsyncContext`, `Callable`, `DeferredResult` và `WriteListener`; giải thích thread, timeout, executor, bảo mật context; rồi triển khai và kiểm thử ứng dụng chạy được.

## 1. Các khái niệm không đồng nghĩa

| Khái niệm | Mục đích | Có thể vẫn blocking không? |
|---|---|---|
| Servlet đồng bộ | Hoàn tất request ngay trong lần dispatch ban đầu | Có, ngay trên container thread |
| Servlet async lifecycle | Giữ response mở trong khi container thread ban đầu đã được trả lại pool | Có, nếu worker làm blocking I/O |
| Asynchronous execution | Chuyển công việc sang worker/executor hoặc chờ sự kiện | Có, worker có thể `sleep`/JDBC |
| Non-blocking I/O | Tránh giữ thread đứng chờ socket/file sẵn sàng; dùng readiness/callback | I/O tương ứng không phải đợi thread; logic khác vẫn có thể block |
| Reactive programming | Compose Publisher/signals; có thể hỗ trợ demand/backpressure | Có thể vẫn blocking nếu dùng thư viện/operation blocking |

Sơ đồ request đơn giản:

~~~text
Client HTTP
   |
Servlet container thread A
   |
Spring MVC Controller
   |
return Callable / DeferredResult
   |
startAsync -> trả thread A về pool
   |
   +-- Callable: worker thread B thực thi, có thể BLOCK
   |
   +-- DeferredResult: chờ event/future; có thể KHÔNG có worker nào đang chờ
   |
Result / Error / Timeout
   |
ASYNC dispatch trên container thread C
   |
Serialize body, HTTP response hoàn tất
~~~

Thread A, B, C có thể khác nhau. Việc request được xử lý async không làm response HTTP xuất hiện ngay; client vẫn phải chờ, và connection cùng các resource khác có thể còn tồn tại.

## 2. Request đồng bộ giữ container thread ra sao?

Một controller minh họa:

~~~java
@RestController
class SlowController {

    @GetMapping("/slow")
    String slow() throws InterruptedException {
        Thread.sleep(200); // request thread bị chặn
        return "ok";
    }
}
~~~

Đây là snippet Spring MVC cần import và dự án Boot. Khi request vào `GET /slow`, thread Servlet xử lý method và đợi 200 ms trước khi trả. Với tải đồng thời lớn, nhiều thread có thể chờ JDBC, filesystem hoặc HTTP client; pool servlet threads hữu hạn có thể cạn.

Tác vụ rất ngắn không cần async bằng mọi giá: thêm async lifecycle/executor/timeout có chi phí. Cần xem yêu cầu thực tế về concurrency và việc phải đợi event/I/O lâu trước khi chọn giải pháp.

## 3. AsyncContext của Jakarta Servlet

Servlet API cho phép khởi động xử lý bất đồng bộ khi servlet/filter tương ứng cho phép async. Các phương thức quan trọng:

- `ServletRequest.startAsync()` bắt đầu async lifecycle và trả `AsyncContext`.
- `ServletRequest.isAsyncStarted()` kiểm tra request đã vào async mode.
- `AsyncContext.start(Runnable)` yêu cầu container đưa Runnable chạy trên thread phù hợp; **Runnable có thể chứa blocking code**.
- `AsyncContext.dispatch()` chuyển request đến dispatch tiếp theo trên container thread.
- `AsyncContext.complete()` hoàn tất async operation theo giao ước Servlet.
- `AsyncContext.setTimeout(long)` đặt timeout theo **milliseconds**.
- `AsyncListener` nhận `onTimeout`, `onError`, `onComplete`, `onStartAsync`.

Một luồng điển hình:

~~~text
REQUEST dispatch
  |
Servlet gọi startAsync()
  |
Method Servlet + filter chain ban đầu kết thúc
  |
Container thread trở lại pool
  |
Request/response vẫn đang ở ASYNC state
  |
  +-- Kết quả có sẵn -> dispatch() hoặc complete()
  +-- Lỗi -> error callback/dispatch hoặc logic xử lý ứng dụng
  +-- Timeout -> onTimeout và timeout/error handling
  |
Response kết thúc
~~~

Khi `startAsync` được gọi, một HTTP response chưa hoàn tất dù servlet method đã return. Trong production, cần đảm bảo đường kết thúc cho cả thành công, lỗi, timeout, client disconnect, đồng thời tránh nhiều thread cùng ghi response.

### 3.1. Ví dụ native Servlet (minh họa cơ chế)

~~~java
import jakarta.servlet.AsyncContext;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

public class NativeAsyncServlet extends HttpServlet {

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {

        AsyncContext async = request.startAsync();
        async.setTimeout(3_000L); // milliseconds

        async.start(() -> {
            try {
                Thread.sleep(100); // blocking trên worker!
                HttpServletResponse target =
                    (HttpServletResponse) async.getResponse();
                target.setContentType("text/plain;charset=UTF-8");
                target.getWriter().write("native async done");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                // Ứng dụng thật cần log và error handling có kiểm soát.
            } catch (IOException ex) {
                // Client có thể đã disconnect; xử lý theo policy.
            } finally {
                async.complete();
            }
        });
    }
}
~~~

Đây **không phải ứng dụng Boot độc lập**; cần Servlet registration với `asyncSupported=true` và filter phù hợp. Demo nhấn mạnh thread ban đầu rời đi nhưng worker vẫn bị chặn bởi `Thread.sleep`. Trong production, timeout có thể đua với worker; không giữ reference response và ghi sau completion. Phải xử lý late result, lỗi, cleanup và terminal state chính xác trước khi dùng thực tế.

Ví dụ registration:

~~~java
@Bean
ServletRegistrationBean<NativeAsyncServlet> nativeAsyncServlet() {
    ServletRegistrationBean<NativeAsyncServlet> bean =
        new ServletRegistrationBean<>(
            new NativeAsyncServlet(), "/native-async");
    bean.setAsyncSupported(true);
    return bean;
}
~~~

Snippet này cần import `@Bean` và `ServletRegistrationBean` trong một `@Configuration`. Các filter custom trên đường đi cũng phải đáp ứng yêu cầu async; một servlet async-supported đơn lẻ không khắc phục filter không tương thích.

## 4. Spring MVC tích hợp Servlet async

Spring MVC có sẵn abstraction cho asynchronous request processing:

| Return type | Nguồn kết quả | Sử dụng thread |
|---|---|---|
| `Callable<T>` | Lambda trả dữ liệu, Spring MVC submit cho `AsyncTaskExecutor` | Worker thực hiện lambda, có thể blocking |
| `WebAsyncTask<T>` | Bọc Callable kèm timeout/executor/callback tùy chọn | Worker từ executor đã chọn |
| `DeferredResult<T>` | Giá trị được callback/event khác gọi `setResult`/`setErrorResult` | Có thể không giữ worker khi chờ event |
| `ResponseBodyEmitter` | Gửi từng phần response theo thời gian | Một số write vẫn blocking qua executor |
| `SseEmitter` | Server-Sent Events | Kết nối lâu, cần timeout/heartbeat/cleanup |
| `StreamingResponseBody` | Ghi lên response OutputStream | Callback thường chạy qua async executor, ghi có thể block |
| Reactive type trong MVC | Kết quả từ Publisher được MVC adapt | Không đồng nghĩa chạy Spring WebFlux |

Spring MVC quản lý `startAsync`, nhận kết quả và async dispatch. Controller sử dụng `Callable` hoặc `DeferredResult` thường **không cần gọi trực tiếp `HttpServletRequest.startAsync()`**.

### 4.1. Callable: công việc chạy ở worker

~~~java
@GetMapping("/api/async/callable")
Callable<Map<String, String>> callable() {
    return () -> {
        Thread.sleep(120);  // worker BLOCKING
        return Map.of("mode", "callable", "value", "ok");
    };
}
~~~

Khi handler trả `Callable`, MVC bắt đầu async lifecycle, submit Callable qua `AsyncTaskExecutor`, rồi trả servlet thread ban đầu. Worker bị sleep 120 ms. Sau khi Callable có kết quả, container xử lý tiếp async dispatch và ghi JSON.

Đây là **asynchronous request**, nhưng không phải **non-blocking computation**. Nó giúp container thread không đứng chờ cả 120 ms; executor vẫn phải có worker.

### 4.2. DeferredResult: chờ callback hoặc sự kiện

~~~java
@GetMapping("/api/async/deferred")
DeferredResult<String> deferred() {
    DeferredResult<String> pending = new DeferredResult<>(3_000L);
    // Đăng ký pending với dịch vụ nhận event/callback.
    return pending;
}

// Khi một event bên ngoài đã tới, ở ngữ cảnh thích hợp:
pending.setResult("done");
~~~

Đây là đoạn minh họa tách hai ngữ cảnh, không phải một class hoàn chỉnh. Với `DeferredResult`, kết quả có thể đến từ JMS callback, external event, HTTP client bất đồng bộ hoặc future được hoàn tất sau. Trong thời gian chờ event, **có thể không có worker đang chờ**.

Nhưng nếu ta thay event bằng:

~~~java
executor.execute(() -> {
    Thread.sleep(120); // worker BLOCKING
    pending.setResult("done");
});
~~~

thì chỉ thay thread bị chặn. Không được kết luận `DeferredResult` luôn non-blocking I/O; cách tạo kết quả mới quyết định điều đó.

### 4.3. WebAsyncTask và timeout riêng

`WebAsyncTask` bọc `Callable` để tùy chỉnh timeout/executor/callback cho request cụ thể:

~~~java
@GetMapping("/api/async/task")
WebAsyncTask<String> task() {
    return new WebAsyncTask<>(2_000L, () -> "ok");
}
~~~

Đây là snippet trong controller, cần import `WebAsyncTask`. Nó thuận tiện khi một endpoint có thời gian chờ khác default. Timeout của HTTP async request không tự ngắt một JDBC query đang chạy; phải có timeout/hủy riêng của thư viện I/O.

## 5. Async execution không đồng nghĩa non-blocking I/O

Có thể tạo future với Java:

~~~java
CompletableFuture<String> value =
    CompletableFuture.supplyAsync(
        () -> legacyClient.load(),
        executor);
~~~

`legacyClient` và `executor` là dependency của ứng dụng. Nếu `load()` sử dụng HTTP client blocking thì thread executor vẫn đứng chờ response. Trong hệ thống Spring, `@Async` cũng chỉ chuyển việc gọi method sang executor khi AOP/proxy được cấu hình đúng; nó không tự biến JDBC thành reactive và không tự giữ HTTP response mở.

Đặc biệt, controller gọi `@Async void` rồi lập tức trả HTTP 200 có thể khiến client được báo thành công trước khi side effect hoàn tất, và lỗi nền không còn gắn với request. Muốn response phụ thuộc công việc, hãy compose kết quả bằng abstraction MVC tương ứng.

### 5.1. Java 17 thuần: async nhưng vẫn block

Tạo file `AsyncNotNonBlocking.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class AsyncNotNonBlocking {
    public static void main(String[] args) {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            CompletableFuture<String> job =
                CompletableFuture.supplyAsync(() -> {
                    try {
                        Thread.sleep(50);  // BLOCK worker
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(ex);
                    }
                    return "done";
                }, pool);

            System.out.println("submitted");
            System.out.println(job.join());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac AsyncNotNonBlocking.java
java AsyncNotNonBlocking
~~~

Stdout chính xác:

~~~text
submitted
done
~~~

`supplyAsync` submit task; main thread tiếp tục đến `println("submitted")`, rồi `join()` chặn main chờ kết quả. Worker cũng chặn 50 ms trong `sleep`. Điều duy nhất được đảm bảo là task được thực hiện qua executor, không phải I/O đã trở thành non-blocking.

## 6. Servlet 3.1 non-blocking I/O: readiness và callback

Servlet 3.1 bổ sung giao diện đọc/ghi dựa trên I/O readiness:
- `ServletInputStream.isReady()` và `setReadListener(ReadListener)`.
- `ServletOutputStream.isReady()` và `setWriteListener(WriteListener)`.
- `ReadListener.onDataAvailable()`, `onAllDataRead()` và `WriteListener.onWritePossible()`.

Trong non-blocking output, ứng dụng chỉ ghi khi stream sẵn sàng, không đứng đợi socket:

~~~text
Register WriteListener
       |
onWritePossible()
       |
while isReady() && có chunk
       |-- write(chunk)
       |
isReady() == false
       |
Return callback, không busy-wait/Thread.sleep
       |
Container báo writable -> onWritePossible() lần sau
       |
Ghi hết dữ liệu -> asyncContext.complete()
~~~

Ví dụ API minh họa:

~~~java
ServletOutputStream stream = response.getOutputStream();

stream.setWriteListener(new WriteListener() {
    @Override
    public void onWritePossible() throws IOException {
        while (stream.isReady() && hasNextChunk()) {
            stream.write(nextChunk());
        }
        if (allChunksWritten()) {
            asyncContext.complete();
        }
    }

    @Override
    public void onError(Throwable cause) {
        reportWriteError(cause);
        asyncContext.complete();
    }
});
~~~

Đây là **pseudocode**, không phải class chạy độc lập: các hàm `hasNextChunk`, `nextChunk`, `allChunksWritten`, `reportWriteError` phải được ứng dụng định nghĩa; `asyncContext` phải ở async mode, callback và state phải thread-safe. Không copy nguyên vào production. Khi `isReady()` trả false, callback phải quay về để container thông báo sau thay vì tự chờ.

**Sự khác biệt:** `AsyncContext.start(() -> blockingJDBC())` vẫn cần worker chặn trong JDBC; `WriteListener` chỉ xử lý socket output readiness không chặn một thread chờ kết nối sẵn sàng. Nếu gọi JDBC hoặc tính toán CPU nặng **bên trong** `onWritePossible()` thì vẫn làm nghẽn callback.

Spring MVC async/streaming **không mặc định** sử dụng hoàn toàn cơ chế non-blocking I/O cấp Servlet: các bước ghi response có thể thực hiện theo blocking write trên executor. WebFlux sử dụng mô hình reactive/non-blocking theo runtime phù hợp; trả một `Flux` từ MVC không tự biến app thành WebFlux.

## 7. Executor của Spring Boot 3.3

Spring Boot 3.3 tự cấu hình `AsyncTaskExecutor` khi các điều kiện phù hợp. Với Java 17, virtual threads không được bật, Boot thường cung cấp `ThreadPoolTaskExecutor`. Trong Spring MVC, bean kiểu `AsyncTaskExecutor` thường có tên `applicationTaskExecutor` để dùng cho async request processing.

Có thể cấu hình:

~~~yaml
spring:
  task:
    execution:
      thread-name-prefix: "demo-async-"
      pool:
        core-size: 4
        max-size: 8
        queue-capacity: 50
        keep-alive: 30s
  mvc:
    async:
      request-timeout: 5s
~~~

Một số tên property dạng đầy đủ:
- `spring.task.execution.pool.core-size`.
- `spring.task.execution.pool.max-size`.
- `spring.task.execution.pool.queue-capacity`.
- `spring.task.execution.pool.keep-alive`.
- `spring.mvc.async.request-timeout`.

**Queue capacity và max-size liên quan chặt chẽ.** Nếu queue không bị giới hạn, tác vụ có thể cứ xếp hàng và pool không tăng tới max-size như kỳ vọng. Cần cân nhắc giới hạn queue, overload/rejection policy, memory và thời gian chờ tối đa.

Đừng nhầm executor này với số **Servlet container threads** (ví dụ `server.tomcat.threads.max` khi dùng Tomcat). Async giúp container threads đỡ bị chiếm, nhưng chuyển việc sang executor không làm tổng workload biến mất. Với JDBC, giới hạn connection pool hoặc database còn có thể là bottleneck lớn hơn số worker.

Nếu ứng dụng tự khai báo `Executor` khác, kiểm tra bean `applicationTaskExecutor` còn tồn tại và đúng kiểu `AsyncTaskExecutor` để Spring MVC sử dụng. Không giả định một bean tên `taskExecutor` tùy ý luôn được MVC chọn.

## 8. Timeout và cancellation không tự truyền xuyên mọi tầng

| Cấu hình/cơ chế | Đang giới hạn gì? |
|---|---|
| `spring.mvc.async.request-timeout` | Thời gian request MVC async chờ trước khi timeout |
| `AsyncContext.setTimeout(ms)` | Timeout của Servlet async operation |
| `DeferredResult<>(timeoutMs)` | Timeout riêng cho một DeferredResult |
| `WebAsyncTask` | Timeout riêng cho Callable wrapper |
| HTTP client connect/read timeout | Kết nối/đọc downstream |
| JDBC/query timeout | Truy vấn database |
| Reverse proxy/ingress timeout | Thời gian proxy chờ upstream |
| Client timeout/disconnect | Thời gian client còn chờ response |

Request async timeout **không bảo đảm** task JDBC đang chạy được ngắt, transaction rollback hoặc HTTP request outbound tự bị hủy. Một worker có thể tiếp tục sau khi client đã bỏ cuộc. Vì thế production cần:
- Timeout downstream riêng.
- Callback timeout/error/completion, cleanup tài nguyên.
- Cancellation propagation khi client/library hỗ trợ.
- Chính sách late-result (không viết vào response đã hoàn tất).
- Không trả HTTP 200 trước khi tác vụ quan trọng thực sự xong.

`DeferredResult.setResult` hoặc `setErrorResult` có thể trả trạng thái cho biết lần set result có được chấp nhận; điều đó không thay cơ chế hủy side effect.

## 9. Ví dụ Spring Boot chạy được: Sync, Callable và DeferredResult

Dự án Java 17+ / Spring Boot 3.3.x có dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là phần dependencies, project vẫn cần Spring Boot plugin, toolchain, Gradle wrapper.

Tạo file `src/main/java/com/example/demo/ServletAsyncApplication.java`:

~~~java
package com.example.demo;

import java.util.Map;
import java.util.concurrent.Callable;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ServletAsyncApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletAsyncApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/async")
class AsyncDemoController {

    private final AsyncTaskExecutor tasks;

    AsyncDemoController(
            @Qualifier("applicationTaskExecutor")
            AsyncTaskExecutor tasks) {
        this.tasks = tasks;
    }

    @GetMapping("/sync")
    Map<String, String> sync() throws InterruptedException {
        Thread.sleep(120);
        return Map.of("mode", "sync", "value", "ok");
    }

    @GetMapping("/callable")
    Callable<Map<String, String>> callable() {
        return () -> {
            Thread.sleep(120); // worker vẫn blocking
            return Map.of("mode", "callable", "value", "ok");
        };
    }

    @GetMapping("/deferred")
    DeferredResult<Map<String, String>> deferred() {
        DeferredResult<Map<String, String>> result =
            new DeferredResult<>(3_000L);

        result.onTimeout(() ->
            result.setErrorResult(new ResponseStatusException(
                HttpStatus.GATEWAY_TIMEOUT,
                "Async request timed out")));

        try {
            tasks.execute(() -> {
                try {
                    Thread.sleep(120); // worker vẫn blocking
                    result.setResult(Map.of(
                        "mode", "deferred", "value", "ok"));
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    result.setErrorResult(new ResponseStatusException(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        "Worker interrupted", ex));
                }
            });
        } catch (TaskRejectedException ex) {
            result.setErrorResult(new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Server busy", ex));
        }
        return result;
    }
}
~~~

Các class nằm cùng package, chỉ `ServletAsyncApplication` public và trùng tên file. Spring Boot 3.3 cung cấp `applicationTaskExecutor` khi auto-configuration phù hợp; nếu dự án tự override executor, phải bảo đảm vẫn có bean đúng tên/kiểu.

Giải thích hành vi:
1. `/sync` block **servlet request thread** khi ngủ.
2. `/callable` trả Callable, Spring MVC chạy nó trong async executor; servlet thread ban đầu được trả về pool.
3. `/deferred` trả holder; `tasks.execute` chạy task và gọi `setResult` sau đó. Worker vẫn block khi ngủ.
4. Khi result có sẵn, MVC tiếp tục xử lý qua async dispatch để serialize JSON response.
5. `DeferredResult<>(3_000L)` đặt timeout riêng cho endpoint này, còn property global có thể là 5 giây.
6. Demo có xử lý rejection cơ bản; production cần overload policy và cancellation/late-result handling đầy đủ.
7. Không phải thêm `@EnableAsync` mới dùng được MVC `Callable`/`DeferredResult`.

Tạo `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  mvc:
    async:
      request-timeout: 5s
  task:
    execution:
      thread-name-prefix: "demo-async-"
      pool:
        core-size: 4
        max-size: 8
        queue-capacity: 50
~~~

Chạy từ Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Gọi ba endpoint:

~~~bash
curl -i http://localhost:8080/api/async/sync
curl -i http://localhost:8080/api/async/callable
curl -i http://localhost:8080/api/async/deferred
~~~

Body JSON (thứ tự key không phải contract):

~~~json
{"mode":"sync","value":"ok"}
~~~

~~~json
{"mode":"callable","value":"ok"}
~~~

~~~json
{"mode":"deferred","value":"ok"}
~~~

Ba endpoint cùng có khoảng ngủ 120 ms để minh họa. Không suy luận chính xác response latency hay tên thread chỉ từ JSON. Đặc điểm cần quan sát là **cơ chế thread và lifecycle**, không phải một lời hứa rằng async luôn nhanh hơn sync.

## 10. Kiểm thử Servlet async với MockMvc

Với một handler trả `Callable` hoặc `DeferredResult`, MockMvc cần hai pha: assert ban đầu đã vào async mode, sau đó gọi `asyncDispatch(mvcResult)` để kiểm tra response cuối.

Tạo file `src/test/java/com/example/demo/ServletAsyncApplicationTest.java`:

~~~java
package com.example.demo;

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
class ServletAsyncApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void callableStartsAsync() throws Exception {
        MvcResult first = mvc.perform(get("/api/async/callable"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(first))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.mode").value("callable"));
    }

    @Test
    void deferredStartsAsync() throws Exception {
        MvcResult first = mvc.perform(get("/api/async/deferred"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(first))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.mode").value("deferred"));
    }

    @Test
    void syncDoesNotStartAsync() throws Exception {
        mvc.perform(get("/api/async/sync"))
            .andExpect(request().asyncNotStarted())
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.mode").value("sync"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

`asyncDispatch` là phần quan trọng: request MockMvc ban đầu chưa tự hoàn tất full container dispatch như một HTTP request thật. Test chứng minh MVC có async lifecycle nhưng **không chứng minh bên trong đã non-blocking I/O** (demo cố tình dùng `Thread.sleep`).

Để kiểm tra servlet container timeout, client disconnect, socket readiness và filter dispatch thật, cần bổ sung test `@SpringBootTest(webEnvironment = RANDOM_PORT)` với HTTP client thực. MockMvc không phải mô hình đầy đủ của socket/servlet container.

## 11. Filter và DispatcherType.ASYNC

Một Servlet muốn `startAsync` hợp lệ phải có `asyncSupported=true`; những filter trong call chain cũng cần tương thích. Nếu filter cần chạy trong async redispatch, cấu hình dispatcher type phù hợp.

Ví dụ `web.xml` trích đoạn:

~~~xml
<filter-mapping>
  <filter-name>traceFilter</filter-name>
  <url-pattern>/*</url-pattern>
  <dispatcher>REQUEST</dispatcher>
  <dispatcher>ASYNC</dispatcher>
</filter-mapping>
~~~

Hoặc qua Spring Boot `FilterRegistrationBean`:

~~~java
FilterRegistrationBean<TraceFilter> bean =
    new FilterRegistrationBean<>(new TraceFilter());

bean.setAsyncSupported(true);
bean.setDispatcherTypes(
    DispatcherType.REQUEST, DispatcherType.ASYNC);
~~~

Đây là các snippet minh họa, cần định nghĩa `TraceFilter` và registration bean đúng cách. Không áp dụng `ASYNC` cho tất cả filter nếu chúng không hỗ trợ gọi lại. Một filter chạy cả REQUEST và ASYNC có thể log hai lần hoặc bọc response hai lần; còn filter chỉ chạy ở REQUEST có thể không quan sát phần hoàn tất. Cần kiểm tra `DispatcherType.ASYNC` và callback lifecycle thực tế.

## 12. Context qua nhiều thread

Một request async có thể đổi thread trong cùng vòng đời HTTP. Những thứ gắn vào `ThreadLocal` không tự động đồng nhất trên tất cả thread:
- MDC/correlation ID dùng cho logs.
- `SecurityContextHolder`.
- `RequestContextHolder`.
- Transaction context.
- Một số request-scoped hoặc tracing context.

Nếu cần, dùng `TaskDecorator`, security-aware executor, context propagation library hoặc truyền dữ liệu rõ qua function argument. Đừng sao chép password/token hoặc giữ request state sống lâu hơn HTTP lifecycle.

Một transaction mở trên servlet thread không tự động chạy trên worker thread. Với JDBC transaction, hãy để service/transaction boundary hình thành đúng trên thread thực hiện công việc thay vì giả định context di chuyển tự động.

## 13. Throughput, tài nguyên và backpressure

Servlet async giúp không phải giữ một servlet thread cho **toàn bộ thời gian chờ response**, nhưng tài nguyên vẫn bị giới hạn:

| Tài nguyên | Điều có thể bị nghẽn | Cách quan sát |
|---|---|---|
| Container threads | Request sync, dispatch/serialization | Active threads, thread pool saturation |
| Async executor threads | JDBC, REST client blocking, sleep | Pool active count, max, rejection |
| Executor queue | Task chờ worker | Queue size, task wait time |
| DB connections | Query chậm hoặc nhiều concurrent requests | Pool active/idle/wait |
| HTTP downstream pool | Connect/read timeout | Connection usage, latency |
| Memory/buffer | Pending requests và streaming | Heap, response buffer, GC |
| Proxy/client timeout | Long-lived response | 499/502/504, disconnect, timeouts |

Ví dụ có 1.000 request cùng thực hiện blocking query kéo dài 1 giây. Servlet async có thể giải phóng thread container ban đầu, nhưng nếu executor có 20 worker thì chỉ một số query blocking có thể chạy đồng thời. Phần còn lại xếp hàng hoặc reject. Async **không làm database nhanh hơn**.

Backpressure của Reactive Streams (`request(n)`) là một cơ chế khác, không tự đồng nghĩa với queue capacity của `ThreadPoolTaskExecutor`. Với streaming cần cân nhắc tốc độ nguồn, buffer, tốc độ client và khả năng hủy.

## 14. So sánh MVC async, WebFlux và virtual threads

| Giải pháp | Phù hợp khi | Cần cảnh giác |
|---|---|---|
| Spring MVC đồng bộ | CRUD đơn giản, I/O nhanh, legacy code | Request threads bị block |
| MVC `Callable` | Muốn tách blocking work ra khỏi container thread | Worker/queue vẫn hữu hạn |
| MVC `DeferredResult` | Kết quả đến từ event/callback thay vì worker đứng chờ | Timeout, cleanup và late completion |
| Servlet ReadListener/WriteListener | Cần non-blocking I/O ở mức Servlet thấp | Callback/state machine phức tạp |
| Spring WebFlux | Có I/O reactive end-to-end, long-lived streams, non-blocking codecs | Blocking trong event loop gây nghẽn |
| Java 21+ virtual threads với MVC | Muốn giữ code tuyến tính với chi phí thread thấp hơn | Không tự đổi blocking I/O thành non-blocking; downstream limits vẫn tồn tại |

Spring Boot 3.3 hỗ trợ virtual threads khi Java 21+ và `spring.threads.virtual.enabled=true`, nhưng bài ví dụ dùng Java 17. Với virtual threads, blocking programming model vẫn có thể là lựa chọn hợp lý; cần chú ý pinning, connection pools và vận hành.

Không quyết định chuyển một ứng dụng MVC sang WebFlux chỉ vì có nhiều request. Trước tiên đo nguyên nhân latency: servlet threads, async queue, database/HTTP pool, CPU, serialization hay reverse proxy.

## 15. Những lỗi thường gặp

1. **Gọi Servlet async là non-blocking.** Async lifecycle chỉ tách việc chờ response khỏi request thread ban đầu.
2. **Đưa `Thread.sleep`/JDBC sang Callable rồi tưởng không còn thread nào bị chặn.** Worker vẫn blocking.
3. **Quên `complete()`/dispatch ở native servlet.** Request pending tới timeout.
4. **Quên timeout/cancellation ở downstream.** Worker còn chạy sau request đã lỗi.
5. **Cho pool/queue tăng vô hạn.** Memory và tail latency bị ảnh hưởng.
6. **Dùng `@Async void` rồi trả 200 ngay.** Client có thể nhận thành công giả.
7. **Mất MDC/security/transaction context khi đổi thread.** Cần propagation có chủ đích.
8. **Sai asyncSupported hoặc filter dispatcher mapping.** Có thể gặp IllegalStateException, missing trace hoặc double logging.
9. **Dùng `SseEmitter`/`StreamingResponseBody` rồi mặc định mọi I/O non-blocking.** Spring MVC có thể ghi blocking qua executor.
10. **Cố ghi response sau timeout/disconnect.** Có thể race và IOException.
11. **Test một lượt MockMvc rồi quên asyncDispatch.** Chưa kiểm tra response cuối.
12. **Trả Mono/Flux từ MVC rồi nghĩ ứng dụng đã là WebFlux.** Runtime quyết định stack.
13. **Giả định virtual threads loại bỏ giới hạn database connections.** Nút cổ chai downstream vẫn còn.

## 16. Checklist và tài liệu tham khảo

- [ ] Đã phân biệt async request lifecycle với non-blocking I/O.
- [ ] Xác định thread nào thực hiện code blocking.
- [ ] Chọn Callable cho task executor; DeferredResult cho event/callback completion.
- [ ] Có bounded executor, queue, rejection policy và metrics.
- [ ] Có timeout MVC, client, proxy và downstream phù hợp.
- [ ] Có xử lý completion/error/timeout/client disconnect và tránh late write.
- [ ] Các custom servlet/filter có `asyncSupported` và dispatch type phù hợp.
- [ ] Đã xem xét MDC, SecurityContext, transaction context khi chuyển thread.
- [ ] Viết MockMvc test với `request().asyncStarted()` và `asyncDispatch`.
- [ ] Có HTTP integration test cho timeout và socket behavior khi cần.
- [ ] Đo p95/p99 latency, pool saturation, database connections trước/sau thay đổi.

Tài liệu chính thức:
- [Spring Framework — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-ann-async.html): Callable, DeferredResult, WebAsyncTask và Servlet async lifecycle.
- [Spring Framework — MockMvc Async Tests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): kiểm thử async request/dispatch.
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): applicationTaskExecutor, pool và queue.
- [Spring Boot 3.3 — Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): MVC async timeout và executor.
- [Jakarta Servlet — AsyncContext API](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/asynccontext): startAsync, complete, dispatch, timeout.
- [Jakarta Servlet — ServletOutputStream API](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/servletoutputstream): isReady, WriteListener.

**Kết luận:** **Servlet async** điều phối vòng đời HTTP request và giải phóng container thread trong lúc response còn chờ. **Non-blocking** là thuộc tính cách thực hiện I/O, cần nguồn và API phù hợp; đưa một lời gọi blocking sang thread khác chỉ là asynchronous execution. Với Spring MVC, phải đo cả executor, downstream, timeout và kết quả kiểm thử trước khi kết luận async giúp hệ thống chịu tải tốt hơn.
